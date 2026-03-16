"""
Validadores reutilizables. Sin dependencias externas.
"""
import re
from django.core.exceptions import ValidationError


# Regex compilado una vez — no recompilar en cada request
_CEDULA_RE = re.compile(r'^[VE]-\d{6,8}$')


def validar_cedula(value: str) -> str:
    """
    Normaliza y valida cédula venezolana.
    Acepta: v27421625, V-27421625, E12345678, e-12345678
    Retorna: V-27421625 (uppercase, con guión)
    Lanza ValidationError si el formato no es recuperable.
    """
    if not value:
        return value

    clean = value.strip().upper().replace('-', '').replace(' ', '')
    if re.match(r'^\d{6,8}$', clean):
        clean = f'V{clean}'

    if not re.match(r'^[VE]\d{6,8}$', clean):
        raise ValidationError(
            'Cédula inválida. Use V-12345678 (venezolano) o E-12345678 (extranjero).'
        )

    return f'{clean[0]}-{clean[1:]}'


def cedula_es_valida(raw: str) -> bool:
    """Versión booleana para guards rápidos sin excepción."""
    if not raw:
        return False
    clean = raw.strip().upper().replace('-', '').replace(' ', '')
    if re.match(r'^\d{6,8}$', clean):
        clean = f'V{clean}'
    return bool(re.match(r'^[VE]\d{6,8}$', clean))


def normalizar_cedula(raw: str) -> str:
    """
    Normaliza sin lanzar excepción.
    Si no es recuperable, retorna el input en uppercase para logging.
    """
    if not raw:
        return ''
    clean = raw.strip().upper().replace('-', '').replace(' ', '')
    if re.match(r'^\d{6,8}$', clean):
        clean = f'V{clean}'
    if re.match(r'^[VE]\d{6,8}$', clean):
        return f'{clean[0]}-{clean[1:]}'
    return raw.strip().upper()
