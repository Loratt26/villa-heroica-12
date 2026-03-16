import os
import sys

# Añadir el directorio actual al path
sys.path.append(os.path.dirname(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asistencia.settings')

# Auto-setup: migraciones + datos iniciales + usuario admin
def _bootstrap():
    try:
        import django
        django.setup()
        from django.core.management import call_command
        call_command('migrate', '--noinput', verbosity=0)

        from control.models import Empleado
        if not Empleado.objects.exists():
            call_command('loaddata', 'control/fixtures/empleados.json', verbosity=0)

        from django.contrib.auth.models import User
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@reportes.com', '123456')
    except Exception as e:
        print(f'Bootstrap error: {e}')

_bootstrap()

from django.core.wsgi import get_wsgi_application
app = get_wsgi_application()
