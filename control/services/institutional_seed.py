from django.db import connection, transaction
from django.db.utils import OperationalError, ProgrammingError

from control.models import Departamento


def ensure_departamentos():
    required = [
        "Limpieza",
        "Seguridad",
        "Coordinación",
        "Dirección",
        "Maestro",
    ]

    table_name = Departamento._meta.db_table

    try:
        if table_name not in connection.introspection.table_names():
            return
    except (OperationalError, ProgrammingError):
        return

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == 'postgresql':
                    cursor.execute(f'LOCK TABLE "{table_name}" IN EXCLUSIVE MODE')

            existentes = set(
                Departamento.objects
                .filter(nombre__in=required)
                .values_list('nombre', flat=True)
            )
            faltantes = [Departamento(nombre=nombre) for nombre in required if nombre not in existentes]
            if faltantes:
                Departamento.objects.bulk_create(faltantes)
    except (OperationalError, ProgrammingError):
        return

    print("Institutional departments ensured")
