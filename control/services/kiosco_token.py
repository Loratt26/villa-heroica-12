"""
Tokens de flujo kiosco.
Un empleado solo puede tener un flujo activo (no expirado, no usado) a la vez.
"""
import secrets
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from ..models import KioscoToken, Empleado

TTL_SEGUNDOS = 180   # 3 minutos


@transaction.atomic
def emitir_token(empleado: Empleado, accion: str) -> str:
    """
    Invalida tokens anteriores del mismo empleado+accion y emite uno nuevo.
    Retorna el token string.
    """
    # Limpiar tokens expirados del empleado de una vez
    KioscoToken.objects.filter(
        empleado=empleado,
        accion=accion,
    ).filter(
        expira_at__lt=timezone.now()
    ).delete()

    # Verificar flujo activo concurrente
    activo = KioscoToken.objects.filter(
        empleado=empleado,
        accion=accion,
        usado=False,
        expira_at__gt=timezone.now(),
    ).first()

    if activo:
        # Reutilizar el token activo — mismo flujo, no duplicar
        return activo.token

    token_str = secrets.token_hex(32)
    KioscoToken.objects.create(
        token=token_str,
        empleado=empleado,
        accion=accion,
        expira_at=timezone.now() + timedelta(seconds=TTL_SEGUNDOS),
    )
    return token_str


@transaction.atomic
def consumir_token(token_str: str, empleado_id: int, accion: str) -> tuple[bool, str]:
    """
    Valida y consume el token.
    Retorna (valido: bool, motivo: str).
    """
    try:
        kt = KioscoToken.objects.select_for_update().get(
            token=token_str,
            empleado_id=empleado_id,
            accion=accion,
        )
    except KioscoToken.DoesNotExist:
        return False, 'TOKEN_INVALIDO'

    if kt.usado:
        return False, 'TOKEN_USADO'

    if timezone.now() >= kt.expira_at:
        return False, 'TOKEN_EXPIRADO'

    kt.usado = True
    kt.save(update_fields=['usado'])
    return True, 'OK'


def limpiar_expirados() -> int:
    """Llamar periódicamente (management command o señal post-request)."""
    deleted, _ = KioscoToken.objects.filter(expira_at__lt=timezone.now()).delete()
    return deleted
