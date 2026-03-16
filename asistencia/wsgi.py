import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asistencia.settings')


def _bootstrap():
    """
    Ejecuta migrate + fixtures + admin en cada arranque en frío.
    Necesario en Railway/Vercel donde el filesystem es efímero.
    """
    try:
        import django
        django.setup()

        from django.core.management import call_command
        from django.db import connection

        # Verificar si las tablas ya existen para no re-migrar innecesariamente
        tablas = connection.introspection.table_names()
        if 'registro_asistencia' not in tablas:
            call_command('migrate', '--noinput', verbosity=0)

            # Cargar fixtures solo si las tablas están vacías
            from control.models import Empleado
            if not Empleado.objects.exists():
                try:
                    call_command('loaddata', 'control/fixtures/empleados.json', verbosity=0)
                except Exception as e:
                    print(f'Fixtures warning: {e}')

        else:
            # Tablas existen — aplicar migraciones pendientes si hay alguna
            call_command('migrate', '--noinput', verbosity=0)

        # Crear usuario admin si no existe (siempre verificar)
        from django.contrib.auth.models import User
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@reportes.com',
                password='123456'
            )

    except Exception as e:
        import traceback
        print(f'Bootstrap error: {e}')
        traceback.print_exc()


_bootstrap()

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
app = application
