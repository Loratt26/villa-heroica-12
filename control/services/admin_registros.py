"""
CRUD admin de registros de asistencia.
Solo accesible por staff autenticado. Registra todo en AuditLog.
"""
from datetime import datetime, date, timedelta
from django.db import transaction
from django.utils import timezone
from ..models import RegistroAsistencia, EstadoRegistro
from .auditoria import registrar as audit

MAX_JORNADA_H = 16


def _coherente(hora_entrada, hora_salida) -> str | None:
    """Retorna código de error o None si es coherente."""
    if not hora_entrada or not hora_salida:
        return None
    if hora_salida <= hora_entrada:
        return 'HORA_INVALIDA'
    diff_h = (
        datetime.combine(date.today(), hora_salida) -
        datetime.combine(date.today(), hora_entrada)
    ).total_seconds() / 3600
    if diff_h > MAX_JORNADA_H:
        return 'JORNADA_EXCESIVA'
    return None


@transaction.atomic
def editar_registro(
    registro_id: int,
    *,
    hora_entrada=None,
    hora_salida=None,
    motivo: str | None = None,
    tipo_novedad: str | None = None,
    editor_empleado=None,
    ip: str = None,
) -> dict:
    """
    Edita campos permitidos de un registro.
    Retorna {'ok': bool, 'codigo': str, 'registro': obj}.
    """
    try:
        registro = RegistroAsistencia.objects.select_for_update().get(pk=registro_id)
    except RegistroAsistencia.DoesNotExist:
        return {'ok': False, 'codigo': 'NO_ENCONTRADO', 'registro': None}

    if registro.estado == EstadoRegistro.CERRADO:
        return {'ok': False, 'codigo': 'REGISTRO_CERRADO', 'registro': registro}

    antes = registro.snapshot()

    # Aplicar solo los campos que se pasan explícitamente
    nueva_entrada = hora_entrada if hora_entrada is not None else registro.hora_entrada
    nueva_salida  = hora_salida  if hora_salida  is not None else registro.hora_salida

    error = _coherente(nueva_entrada, nueva_salida)
    if error:
        return {'ok': False, 'codigo': error, 'registro': registro}

    update_fields = ['updated_at']

    if hora_entrada is not None:
        registro.hora_entrada = hora_entrada
        update_fields.append('hora_entrada')
        # Actualizar estado si antes no había entrada
        if hora_entrada and registro.estado == EstadoRegistro.SIN_ENTRADA:
            registro.estado = EstadoRegistro.ENTRADA_REGISTRADA
            update_fields.append('estado')

    if hora_salida is not None:
        registro.hora_salida = hora_salida
        update_fields.append('hora_salida')
        if hora_salida and registro.estado == EstadoRegistro.ENTRADA_REGISTRADA:
            registro.estado = EstadoRegistro.SALIDA_REGISTRADA
            update_fields.append('estado')

    if motivo is not None:
        registro.motivo = motivo
        update_fields.append('motivo')

    if tipo_novedad is not None:
        opciones_validas = {c[0] for c in RegistroAsistencia.NOVEDAD}
        if tipo_novedad not in opciones_validas:
            return {'ok': False, 'codigo': 'NOVEDAD_INVALIDA', 'registro': registro}
        registro.tipo_novedad = tipo_novedad
        update_fields.append('tipo_novedad')

    registro.save(update_fields=update_fields)

    audit(
        'EDIT_REGISTRO',
        empleado=registro.empleado,
        realizado_por=editor_empleado,
        ip=ip,
        antes=antes,
        despues=registro.snapshot(),
        registro_id=registro.pk,
        fecha=str(registro.fecha),
    )

    return {'ok': True, 'codigo': 'EDITADO', 'registro': registro}


@transaction.atomic
def eliminar_registro(
    registro_id: int,
    *,
    editor_empleado=None,
    ip: str = None,
    motivo_eliminacion: str = '',
) -> dict:
    """
    Elimina un registro. Solo permitido si NO está en estado CERRADO.
    """
    try:
        registro = RegistroAsistencia.objects.select_for_update().get(pk=registro_id)
    except RegistroAsistencia.DoesNotExist:
        return {'ok': False, 'codigo': 'NO_ENCONTRADO'}

    if registro.estado == EstadoRegistro.CERRADO:
        return {'ok': False, 'codigo': 'REGISTRO_CERRADO'}

    snapshot = registro.snapshot()
    snapshot['fecha'] = str(registro.fecha)
    snapshot['empleado'] = str(registro.empleado)

    audit(
        'DEL_REGISTRO',
        empleado=registro.empleado,
        realizado_por=editor_empleado,
        ip=ip,
        antes=snapshot,
        motivo_eliminacion=motivo_eliminacion,
        registro_id=registro_id,
    )

    registro.delete()
    return {'ok': True, 'codigo': 'ELIMINADO'}
