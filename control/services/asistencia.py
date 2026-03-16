"""
Service layer de asistencia.
State machine + AuditLog + validaciones institucionales.
"""
import hashlib
import logging
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from ..models import Empleado, EstadoRegistro, Feriado, RegistroAsistencia
from .auditoria import audit_marcaje
from .tardanzas import sync_tardanza_alert_for_employee_week

logger = logging.getLogger('control.asistencia')

TARDANZA_MIN = getattr(settings, 'KIOSCO_TOLERANCIA_TARDANZA_MIN', 20)
SALIDA_ANT_MIN = 20
MAX_JORNADA_H = 16
DEPARTAMENTOS_AUTORIZADORES = ['Direcci\u00f3n', 'Coordinaci\u00f3n']


def _minutos_entre(t1: time, t2: time) -> int:
    base = date.today()
    return int((datetime.combine(base, t2) - datetime.combine(base, t1)).total_seconds() // 60)


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


def _validar_hora_entrada(hora: time) -> str | None:
    ahora = timezone.localtime().time()
    hoy = date.today()
    if datetime.combine(hoy, hora) > datetime.combine(hoy, ahora) + timedelta(minutes=5):
        return 'HORA_FUTURA'
    return None


def _validar_hora_salida(hora_salida: time, hora_entrada: time) -> str | None:
    ahora = timezone.localtime().time()
    hoy = date.today()
    if datetime.combine(hoy, hora_salida) > datetime.combine(hoy, ahora) + timedelta(minutes=5):
        return 'HORA_FUTURA'
    if hora_salida <= hora_entrada:
        return 'HORA_INVALIDA'
    diff_h = _minutos_entre(hora_entrada, hora_salida) / 60
    if diff_h > MAX_JORNADA_H:
        return 'JORNADA_EXCESIVA'
    return None


def _autorizadores_queryset():
    return Empleado.objects.filter(
        departamento__nombre__in=DEPARTAMENTOS_AUTORIZADORES,
        activo=True,
    ).select_related('departamento').order_by('apellido', 'nombre')


def _serializar_autorizadores(queryset):
    return list(queryset.values('id', 'nombre', 'apellido', 'cedula'))


def _evaluacion_salida_base() -> dict:
    return {
        'estado': 'normal_exit',
        'mensaje': '',
        'minutos': 0,
        'codigo': '',
        'requiere_justificante': False,
        'requires_justification': False,
        'requiere_motivo': False,
        'requires_motivo': False,
        'requiere_autorizacion': False,
        'requires_authorization': False,
        'authorized_list': Empleado.objects.none(),
        'autorizadores': [],
    }


def serializar_evaluacion(evaluacion: dict) -> dict:
    data = dict(evaluacion)
    authorized_list = data.get('authorized_list')
    if hasattr(authorized_list, 'values'):
        data['authorized_list'] = _serializar_autorizadores(authorized_list)
    elif authorized_list is None:
        data['authorized_list'] = []
    data['autorizadores'] = data.get('autorizadores') or data['authorized_list']
    data['requires_motivo'] = data.get('requires_motivo', data.get('requiere_motivo', False))
    data['requires_justification'] = data.get(
        'requires_justification',
        data.get('requiere_justificante', False),
    )
    data['requires_authorization'] = data.get(
        'requires_authorization',
        data.get('requiere_autorizacion', False),
    )
    return data


def _es_dia_laborable(empleado: Empleado, fecha: date) -> bool:
    if Feriado.objects.filter(fecha=fecha).exists():
        return False
    return empleado.es_dia_laborable(fecha)


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


def evaluar_salida(
    empleado: Empleado,
    hora: time,
    registro: RegistroAsistencia | None = None,
) -> dict:
    evaluacion = _evaluacion_salida_base()

    if not empleado.hora_salida:
        return evaluacion

    faltan = _minutos_entre(hora, empleado.hora_salida)
    if faltan >= SALIDA_ANT_MIN:
        authorized_list = _autorizadores_queryset()
        evaluacion.update({
            'estado': 'requires_justification',
            'requiere_justificante': True,
            'requires_justification': True,
            'requiere_motivo': True,
            'requires_motivo': True,
            'requiere_autorizacion': True,
            'requires_authorization': True,
            'mensaje': (
                f'Faltan {faltan} minutos para tu hora de salida '
                f'({empleado.hora_salida.strftime("%I:%M %p")}). '
                f'Se requiere motivo y autorizacion.'
            ),
            'minutos': faltan,
            'authorized_list': authorized_list,
            'autorizadores': _serializar_autorizadores(authorized_list),
        })
    return evaluacion


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

    error_hora = _validar_hora_entrada(hora)
    if error_hora:
        return {'ok': False, 'codigo': error_hora, 'registro': None}

    hoy = timezone.localdate()
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
                'ok': False,
                'codigo': 'ENTRADA_DUPLICADA',
                'hora_existente': registro.hora_entrada,
                'registro': registro,
            }

        campos_motivo = motivo.strip() if evaluacion['requiere_motivo'] else ''

        if registro:
            if not registro.transicionar(EstadoRegistro.ENTRADA_REGISTRADA):
                return {'ok': False, 'codigo': 'ESTADO_INVALIDO', 'registro': registro}

            registro.hora_entrada = hora
            registro.tipo_novedad = evaluacion['estado']
            registro.motivo = campos_motivo
            registro.ip_kiosco = ip
            if not registro.horario_entrada_esperado and empleado.hora_entrada:
                registro.horario_entrada_esperado = empleado.hora_entrada
            registro.save(update_fields=[
                'hora_entrada',
                'tipo_novedad',
                'motivo',
                'ip_kiosco',
                'estado',
                'horario_entrada_esperado',
                'updated_at',
            ])
        else:
            registro = RegistroAsistencia(
                empleado=empleado,
                fecha=hoy,
                hora_entrada=hora,
                tipo_novedad=evaluacion['estado'],
                motivo=campos_motivo,
                ip_kiosco=ip,
                horario_entrada_esperado=empleado.hora_entrada,
                horario_salida_esperado=empleado.hora_salida,
                estado=EstadoRegistro.ENTRADA_REGISTRADA,
            )
            registro.save()

        resultado = {
            'ok': True,
            'codigo': 'ENTRADA_OK',
            'registro': registro,
            'evaluacion': evaluacion,
        }
        audit_marcaje(resultado, 'entrada', empleado, ip)
        sync_tardanza_alert_for_employee_week(empleado, hoy)
        return resultado

    except IntegrityError:
        try:
            registro = RegistroAsistencia.objects.get(empleado=empleado, fecha=hoy)
        except RegistroAsistencia.DoesNotExist:
            registro = None
        return {
            'ok': False,
            'codigo': 'ENTRADA_DUPLICADA',
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

    hoy = timezone.localdate()

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
                'ok': False,
                'codigo': 'SALIDA_DUPLICADA',
                'hora_existente': registro.hora_salida,
                'registro': registro,
            }

        error_hora = _validar_hora_salida(hora, registro.hora_entrada)
        if error_hora:
            return {'ok': False, 'codigo': error_hora, 'registro': None}

        evaluacion = evaluar_salida(empleado, hora, registro=registro)
        if evaluacion['requiere_motivo'] and not motivo.strip():
            return {'ok': False, 'codigo': 'MOTIVO_REQUERIDO', 'registro': registro}

        autorizador = None
        if evaluacion.get('requiere_autorizacion'):
            if not autorizado_por_id:
                return {'ok': False, 'codigo': 'AUTORIZACION_REQUERIDA', 'registro': registro}
            try:
                autorizado_por_id = int(autorizado_por_id)
            except (TypeError, ValueError):
                return {'ok': False, 'codigo': 'AUTORIZACION_INVALIDA', 'registro': registro}
            if autorizado_por_id == empleado.pk:
                return {'ok': False, 'codigo': 'AUTORIZACION_INVALIDA', 'registro': registro}
            try:
                autorizador = _autorizadores_queryset().get(pk=autorizado_por_id)
            except Empleado.DoesNotExist:
                return {'ok': False, 'codigo': 'AUTORIZACION_INVALIDA', 'registro': registro}

        if not registro.transicionar(EstadoRegistro.SALIDA_REGISTRADA):
            return {'ok': False, 'codigo': 'ESTADO_INVALIDO', 'registro': registro}

        if not registro.horario_salida_esperado and empleado.hora_salida:
            registro.horario_salida_esperado = empleado.hora_salida

        registro.hora_salida = hora
        registro.fecha_salida = None
        registro.autorizado_por = autorizador
        registro.ip_kiosco = ip

        if evaluacion['requiere_motivo']:
            registro.motivo = motivo.strip()
            registro.tipo_novedad = 'salida_anticipada'
        elif not registro.tipo_novedad:
            registro.tipo_novedad = 'normal'

        registro.save(update_fields=[
            'hora_salida',
            'fecha_salida',
            'motivo',
            'autorizado_por',
            'tipo_novedad',
            'estado',
            'ip_kiosco',
            'horario_salida_esperado',
            'updated_at',
        ])

        resultado = {
            'ok': True,
            'codigo': 'SALIDA_OK',
            'registro': registro,
            'evaluacion': evaluacion,
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
            'ok': False,
            'codigo': 'SALIDA_DUPLICADA',
            'hora_existente': registro.hora_salida if registro else None,
            'registro': registro,
        }
    except OperationalError as e:
        logger.error('registrar_salida OperationalError emp=%s: %s', empleado.pk, e)
        return {'ok': False, 'codigo': 'ERROR_DB', 'registro': None, 'detalle': str(e)}
