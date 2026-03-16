"""
Cache de autofill para la API de cédula.
Evita queries a DB en cada keystroke.
Rate limiting simple sin librerías externas.
"""
from django.core.cache import cache
from django.utils import timezone
from ..models import Empleado, RegistroAsistencia
from ..validators import normalizar_cedula, cedula_es_valida

_CACHE_TTL_EMPLEADO = 300   # 5 min — datos del empleado cambian poco
_RATE_LIMIT_MAX     = 30    # máximo requests por ventana
_RATE_LIMIT_WINDOW  = 60    # segundos


def _rate_key(ip: str) -> str:
    return f'rl:autofill:{ip}'


def check_rate_limit(ip: str) -> bool:
    """True = permitido. False = límite superado."""
    if not ip:
        return True
    key   = _rate_key(ip)
    count = cache.get(key, 0)
    if count >= _RATE_LIMIT_MAX:
        return False
    # Increment atómico — usa add para inicializar con TTL correcto
    if count == 0:
        cache.set(key, 1, timeout=_RATE_LIMIT_WINDOW)
    else:
        cache.incr(key)
    return True


def _empleado_cache_key(cedula: str) -> str:
    return f'emp:cedula:{cedula}'


def buscar_empleado_cached(cedula_raw: str) -> dict:
    """
    Busca empleado por cédula con cache.
    Retorna dict listo para JsonResponse.
    No lanza excepciones.
    """
    if not cedula_es_valida(cedula_raw):
        return {'encontrado': False, 'error': 'formato_invalido'}

    cedula = normalizar_cedula(cedula_raw)
    cache_key = _empleado_cache_key(cedula)

    cached = cache.get(cache_key)
    if cached:
        # Completar con datos del día (no se cachean — cambian durante el día)
        cached = _enriquecer_con_estado_dia(cached)
        return cached

    # Miss de caché — query a DB
    try:
        emp = (
            Empleado.objects
            .select_related('departamento')
            .get(cedula=cedula)
        )
    except Empleado.DoesNotExist:
        return {'encontrado': False, 'error': 'no_registrado'}

    if not emp.activo:
        return {'encontrado': False, 'error': 'inactivo'}

    base = {
        'encontrado':   True,
        'id':           emp.pk,
        'nombre':       emp.nombre,
        'apellido':     emp.apellido,
        'cargo':        emp.cargo,
        'departamento': emp.departamento.nombre,
        'foto_url':     emp.foto.url if emp.foto else None,
        '_cedula':      cedula,
    }

    # Guardar en caché solo los datos estables del empleado
    cache.set(cache_key, base, timeout=_CACHE_TTL_EMPLEADO)

    return _enriquecer_con_estado_dia(base)


def _enriquecer_con_estado_dia(base: dict) -> dict:
    """Agrega estado del día (entrada/salida) y evaluaciones. No se cachea."""
    from .asistencia import evaluar_entrada, evaluar_salida, serializar_evaluacion

    emp_id = base['id']
    hoy    = timezone.localdate()
    ahora  = timezone.localtime().time()

    reg_hoy = RegistroAsistencia.objects.filter(
        empleado_id=emp_id, fecha=hoy
    ).only('hora_entrada', 'hora_salida').first()

    try:
        emp = Empleado.objects.get(pk=emp_id)
        eval_entrada = serializar_evaluacion(evaluar_entrada(emp, ahora))
        eval_salida = serializar_evaluacion(evaluar_salida(emp, ahora, registro=reg_hoy))
    except Empleado.DoesNotExist:
        eval_entrada = eval_salida = {'estado': 'normal', 'requiere_motivo': False, 'mensaje': ''}

    result = {**base}
    result.pop('_cedula', None)
    result.update({
        'tiene_entrada':    bool(reg_hoy and reg_hoy.hora_entrada),
        'tiene_salida':     bool(reg_hoy and reg_hoy.hora_salida),
        'hora_entrada_hoy': (
            reg_hoy.hora_entrada.strftime('%H:%M')
            if reg_hoy and reg_hoy.hora_entrada else None
        ),
        'evaluacion_entrada': eval_entrada,
        'evaluacion_salida':  eval_salida,
    })
    return result


def invalidar_cache_empleado(cedula: str) -> None:
    """Llamar cuando se edita un empleado para limpiar su caché."""
    if cedula:
        cache.delete(_empleado_cache_key(normalizar_cedula(cedula)))
