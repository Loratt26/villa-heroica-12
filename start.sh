#!/bin/bash

echo "================================================"
echo "  Colegio Villa Heroica - Sistema Asistencia"
echo "================================================"

if [ -n "${DATABASE_URL:-}" ]; then
    echo "Using PostgreSQL production database"
else
    echo "Using SQLite development database"
fi

echo ""
echo "==> [1/5] Creando directorios..."
mkdir -p /tmp/logs media staticfiles

echo "==> [2/5] Aplicando migraciones..."
python manage.py migrate --noinput
MIGRATE_EXIT=$?
if [ $MIGRATE_EXIT -ne 0 ]; then
    echo "CRITICO: migrate fallo con codigo $MIGRATE_EXIT"
    exit 1
fi
echo "Migraciones aplicadas correctamente."

echo "==> [3/5] Cargando datos iniciales..."
python manage.py shell -c "
from django.core.management import call_command
from control.models import Empleado
if Empleado.objects.exists():
    print('Empleados existentes detectados. No se cargan fixtures.')
else:
    call_command('loaddata', 'control/fixtures/empleados.json')
    print('Fixtures cargados.')
"

echo "==> [4/5] Creando usuario admin..."
python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@reportes.com', '123456')
    print('Usuario admin creado: admin / 123456')
else:
    print('Usuario admin ya existe.')
"

echo "==> [5/5] Iniciando gunicorn en puerto ${PORT:-8000}..."
exec gunicorn asistencia.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
