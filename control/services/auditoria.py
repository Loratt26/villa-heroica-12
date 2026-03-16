"""
Servicio de auditoría.
Llamar DENTRO de transaction.atomic() del service principal para garantizar
atomicidad: si la operación principal falla, el audit también se revierte.
"""
import logging
from django.utils import timezone
from ..models import AuditLog, Empleado, RegistroAsistencia

logger = logging.getLogger('control.auditoria')


def registrar(
    accion: str,
    *,
    empleado: Empleado | None = None,
    realizado_por: Empleado | None = None,
    ip: str | None = None,
    antes: dict | None = None,
    despues: dict | None = None,
    **metadata,
) -> None:
    """
    Crea un registro de auditoría.
    No lanza excepción — loggea si falla para no interrumpir el flujo principal.
    """
    try:
        AuditLog.objects.create(
            accion=accion,
            empleado=empleado,
            realizado_por=realizado_por,
            ip_address=ip,
            datos_antes=antes,
            datos_despues=despues,
            metadata=metadata or {},
        )
    except Exception as e:
        logger.error('audit_fail accion=%s error=%s', accion, e)


def audit_marcaje(resultado: dict, accion: str, empleado: Empleado, ip: str) -> None:
    """Wrapper específico para marcajes desde kiosco y admin."""
    if not resultado.get('ok'):
        return
    registro: RegistroAsistencia = resultado['registro']
    eval_ = resultado.get('evaluacion', {})
    estado = eval_.get('estado', 'normal')

    accion_audit = {
        ('entrada', 'normal'):           'ENTRADA',
        ('entrada', 'tardanza'):         'TARDANZA',
        ('salida',  'normal'):           'SALIDA',
        ('salida',  'salida_anticipada'): 'SALIDA_ANT',
    }.get((accion, estado), 'ENTRADA' if accion == 'entrada' else 'SALIDA')

    registrar(
        accion_audit,
        empleado=empleado,
        ip=ip,
        despues=registro.snapshot(),
        registro_id=registro.pk,
        minutos=eval_.get('minutos', 0),
    )
