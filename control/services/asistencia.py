"""
Service layer de asistencia — hardened v3.
State machine + AuditLog + validaciones de hora + turnos nocturnos.
"""
import hashlib
import logging
from datetime import datetime, date, time, timedelta
from django.db import transaction, IntegrityError, OperationalError
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings

from ..models import Empleado, RegistroAsistencia, EstadoRegistro, Feriado
from .auditoria import registrar as audit, audit_marcaje
from .tardanzas import sync_tardanza_alert_for_employee_week

logger = logging.getLogger('control.asistencia')

TARDANZA_MIN   = getattr(settings, 'KIOSCO_TOLERANCIA_TARDANZA_MIN', 20)
SALIDA_ANT_MIN = getattr(settings, 'KIOSCO_TOLERANCIA_SALIDA_ANT_MIN', 40)
MAX_JORNADA_H  = 16   # más de 16h entre entrada y salida es imposible


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _minutos_entre(t1: time, t2: time) -> int:
    base = date.today()
    return int(
        (datetime.combine(base, t2) - datetime.combine(base, t1)).total_seconds() // 60
    )


def _get_ip(request) -> str | None:
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')


def _idempotency_key(empleado_id: int, accion: str, fecha) -> str:
    raw = f'marcaje:{empleado_id}:{accion}:{fecha}'
    return hashlib.md5(raw.encode()).hexdigest()


def _check_and_set_idempotency(empleado_id: int, accion: str) -> bool:
    key = _idempotency_key(empleado_id, accion, timezone.localdate())
    if cache.get(key):
        return False
    cache.set(key, 1, timeout=10)
    return True


# ─── Validaciones de hora ─────────────────────────────────────────────────────

def _validar_hora_entrada(hora: time) -> str | None:
    """Retorna código de error o None si es válida."""
    ahora = timezone.localtime().time()
    # Hora futura: más de 5 minutos en el futuro (margen para relojes desincronizados)
    hoy = date.today()
    if datetime.combine(hoy, hora) > datetime.combine(hoy, ahora) + timedelta(minutes=5):
        return 'HORA_FUTURA'
    return None


def _validar_hora_salida(hora_salida: time, hora_entrada: time) -> str | None:
    ahora = timezone.localtime().time()
    hoy   = date.today()
    # Hora futura
    if datetime.combine(hoy, hora_salida) > datetime.combine(hoy, ahora) + timedelta(minutes=5):
        return 'HORA_FUTURA'
    # Salida <= entrada (mismo día)
    if hora_salida <= hora_entrada:
        return 'HORA_INVALIDA'
    # Jornada irrazonablemente larga
    diff_h = _minutos_entre(hora_entrada, hora_salida) / 60
    if diff_h > MAX_JORNADA_H:
        return 'JORNADA_EXCESIVA'
    return None


def _es_dia_laborable(empleado: Empleado, fecha: date) -> bool:
    """Feriados + días laborables del empleado."""
    if Feriado.objects.filter(fecha=fecha).exists():
        return False
    return empleado.es_dia_laborable(fecha)


# ─── Evaluación (sin escritura en DB) ─────────────────────────────────────────

def evaluar_entrada(empleado: Empleado, hora: time) -> dict:
    if not empleado.hora_entrada:
        return {'estado': 'normal', 'requiere_motivo': False, 'mensaje': ''}

    diff = _minutos_entre(empleado.hora_entrada, hora)
    if diff >= TARDANZA_MIN:
        return {
            'estado': 'tardanza',
            'requiere_motivo': True,
            'requiere_autorizacion': False,
            'mensaje': (
                f'Llegas {diff} minutos tarde. '
                f'Tu hora de entrada es {empleado.hora_entrada.strftime("%I:%M %p")}.'
            ),
            'minutos': diff,
        }
    return {'estado': 'normal', 'requiere_motivo': False, 'mensaje': ''}


def evaluar_salida(empleado: Empleado, hora: time) -> dict:
    if not empleado.hora_salida:
        return {'estado': 'normal', 'requiere_motivo': False, 'mensaje': ''}

    faltan = _minutos_entre(hora, empleado.hora_salida)
    if 0 < faltan <= SALIDA_ANT_MIN:
        autorizadores = list(
            Empleado.objects.filter(
                activo=True,
                departamento__nombre__in=['Coordinación', 'Dirección'],
            ).values('id', 'nombre', 'apellido')
        )
        return {
            'estado': 'salida_anticipada',
            'requiere_motivo': True,
            'requiere_autorizacion': True,
            'mensaje': (
                f'Faltan {faltan} minutos para tu hora de salida '
                f'({empleado.hora_salida.strftime("%I:%M %p")}). '
                f'Se requiere motivo y autorización.'
            ),
            'minutos': faltan,
            'autorizadores': autorizadores,
        }
    return {'estado': 'normal', 'requiere_motivo': False, 'mensaje': ''}


# ─── Escritura atómica ────────────────────────────────────────────────────────

@transaction.atomic
def registrar_entrada(
    empleado: Empleado,
    hora: time,
    motivo: str = '',
    ip: str = None,
) -> dict:
    if not empleado.activo:
        return {'ok': False, 'codigo': 'EMPLEADO_INACTIVO', 'registro': None}

    if not _check_and_set_idempotency(empleado.pk, 'entrada'):
        return {'ok': False, 'codigo': 'DOBLE_SUBMIT', 'registro': None}

    # Validar hora antes de cualquier operación DB
    error_hora = _validar_hora_entrada(hora)
    if error_hora:
        return {'ok': False, 'codigo': error_hora, 'registro': None}

    hoy        = timezone.localdate()
    evaluacion = evaluar_entrada(empleado, hora)

    if evaluacion['requiere_motivo'] and not motivo.strip():
        return {'ok': False, 'codigo': 'MOTIVO_REQUERIDO', 'registro': None}

    try:
        registro = (
            RegistroAsistencia.objects
            .select_for_update(nowait=False)
            .filter(empleado=empleado, fecha=hoy)
            .first()
        )

        if registro and registro.hora_entrada:
            return {
                'ok': False, 'codigo': 'ENTRADA_DUPLICADA',
                'hora_existente': registro.hora_entrada, 'registro': registro,
            }

        campos_motivo = motivo.strip() if evaluacion['requiere_motivo'] else ''

        if registro:
            # Validar transición de estado
            if not registro.transicionar(EstadoRegistro.ENTRADA_REGISTRADA):
                return {'ok': False, 'codigo': 'ESTADO_INVALIDO', 'registro': registro}

            registro.hora_entrada = hora
            registro.tipo_novedad = evaluacion['estado']
            registro.motivo       = campos_motivo
            registro.ip_kiosco    = ip
            if not registro.horario_entrada_esperado and empleado.hora_entrada:
                registro.horario_entrada_esperado = empleado.hora_entrada
            registro.save(update_fields=[
                'hora_entrada', 'tipo_novedad', 'motivo', 'ip_kiosco',
                'estado', 'horario_entrada_esperado', 'updated_at',
            ])
        else:
            registro = RegistroAsistencia(
                empleado                 = empleado,
                fecha                    = hoy,
                hora_entrada             = hora,
                tipo_novedad             = evaluacion['estado'],
                motivo                   = campos_motivo,
                ip_kiosco                = ip,
                horario_entrada_esperado = empleado.hora_entrada,
                horario_salida_esperado  = empleado.hora_salida,
                estado                   = EstadoRegistro.ENTRADA_REGISTRADA,
            )
            registro.save()

        resultado = {
            'ok': True, 'codigo': 'ENTRADA_OK',
            'registro': registro, 'evaluacion': evaluacion,
        }
        # Auditoría dentro de la misma transacción
        audit_marcaje(resultado, 'entrada', empleado, ip)
        sync_tardanza_alert_for_employee_week(empleado, hoy)
        return resultado

    except IntegrityError:
        try:
            registro = RegistroAsistencia.objects.get(empleado=empleado, fecha=hoy)
        except RegistroAsistencia.DoesNotExist:
            registro = None
        return {
            'ok': False, 'codigo': 'ENTRADA_DUPLICADA',
            'hora_existente': registro.hora_entrada if registro else None,
            'registro': registro,
        }
    except OperationalError as e:
        logger.error('registrar_entrada OperationalError emp=%s: %s', empleado.pk, e)
        return {'ok': False, 'codigo': 'ERROR_DB', 'registro': None, 'detalle': str(e)}


@transaction.atomic
def registrar_salida(
    empleado: Empleado,
    hora: time,
    motivo: str = '',
    autorizado_por_id: int = None,
    ip: str = None,
) -> dict:
    if not empleado.activo:
        return {'ok': False, 'codigo': 'EMPLEADO_INACTIVO', 'registro': None}

    if not _check_and_set_idempotency(empleado.pk, 'salida'):
        return {'ok': False, 'codigo': 'DOBLE_SUBMIT', 'registro': None}

    hoy        = timezone.localdate()
    evaluacion = evaluar_salida(empleado, hora)

    if evaluacion['requiere_motivo'] and not motivo.strip():
        return {'ok': False, 'codigo': 'MOTIVO_REQUERIDO', 'registro': None}

    autorizador = None
    if evaluacion.get('requiere_autorizacion'):
        if not autorizado_por_id:
            return {'ok': False, 'codigo': 'AUTORIZACION_REQUERIDA', 'registro': None}
        try:
            autorizado_por_id = int(autorizado_por_id)
        except (TypeError, ValueError):
            return {'ok': False, 'codigo': 'AUTORIZACION_INVALIDA', 'registro': None}
        if autorizado_por_id == empleado.pk:
            return {'ok': False, 'codigo': 'AUTORIZACION_INVALIDA', 'registro': None}
        try:
            autorizador = Empleado.objects.get(
                pk=autorizado_por_id, activo=True,
                departamento__nombre__in=['Coordinación', 'Dirección'],
            )
        except Empleado.DoesNotExist:
            return {'ok': False, 'codigo': 'AUTORIZACION_INVALIDA', 'registro': None}

    try:
        registro = (
            RegistroAsistencia.objects
            .select_for_update(nowait=False)
            .filter(empleado=empleado, fecha=hoy)
            .first()
        )

        if not registro or not registro.hora_entrada:
            return {'ok': False, 'codigo': 'SIN_ENTRADA', 'registro': None}

        if registro.hora_salida:
            return {
                'ok': False, 'codigo': 'SALIDA_DUPLICADA',
                'hora_existente': registro.hora_salida, 'registro': registro,
            }

        # Validar hora de salida contra la entrada real del registro
        error_hora = _validar_hora_salida(hora, registro.hora_entrada)
        if error_hora:
            return {'ok': False, 'codigo': error_hora, 'registro': None}

        # Turno nocturno: si hora < hora_entrada, la salida es el día siguiente
        fecha_salida = hoy
        if hora < registro.hora_entrada:
            fecha_salida = hoy + timedelta(days=1)

        # Snapshot antes para auditoría
        antes = registro.snapshot()

        if not registro.transicionar(EstadoRegistro.SALIDA_REGISTRADA):
            return {'ok': False, 'codigo': 'ESTADO_INVALIDO', 'registro': registro}

        if not registro.horario_salida_esperado and empleado.hora_salida:
            registro.horario_salida_esperado = empleado.hora_salida

        registro.hora_salida    = hora
        registro.fecha_salida   = fecha_salida if fecha_salida != hoy else None
        registro.autorizado_por = autorizador
        registro.ip_kiosco      = ip

        if evaluacion['requiere_motivo']:
            nuevo = motivo.strip()
            registro.motivo = (
                f'{registro.motivo} | {nuevo}' if registro.motivo and registro.motivo != nuevo
                else nuevo
            )

        prioridad = {'normal': 0, 'tardanza': 1, 'salida_anticipada': 2}
        if prioridad.get(evaluacion['estado'], 0) > prioridad.get(registro.tipo_novedad, 0):
            registro.tipo_novedad = evaluacion['estado']

        registro.save(update_fields=[
            'hora_salida', 'fecha_salida', 'motivo', 'autorizado_por', 'tipo_novedad',
            'estado', 'ip_kiosco', 'horario_salida_esperado', 'updated_at',
        ])

        resultado = {
            'ok': True, 'codigo': 'SALIDA_OK',
            'registro': registro, 'evaluacion': evaluacion,
        }
        audit_marcaje(resultado, 'salida', empleado, ip)
        sync_tardanza_alert_for_employee_week(empleado, hoy)
        return resultado

    except IntegrityError:
        try:
            registro = RegistroAsistencia.objects.get(empleado=empleado, fecha=hoy)
        except RegistroAsistencia.DoesNotExist:
            registro = None
        return {
            'ok': False, 'codigo': 'SALIDA_DUPLICADA',
            'hora_existente': registro.hora_salida if registro else None,
            'registro': registro,
        }
    except OperationalError as e:
        logger.error('registrar_salida OperationalError emp=%s: %s', empleado.pk, e)
        return {'ok': False, 'codigo': 'ERROR_DB', 'registro': None, 'detalle': str(e)}
