#!/bin/bash

echo "================================================"
echo "  Colegio Villa Heroica — Sistema Asistencia"
echo "================================================"
echo "DB path: $(python -c 'import django, os; os.environ[\"DJANGO_SETTINGS_MODULE\"]=\"asistencia.settings\"; django.setup(); from django.conf import settings; print(settings.DATABASES[\"default\"][\"NAME\"])' 2>/dev/null || echo 'calculando...')"

echo ""
echo "==> [1/5] Creando directorios..."
mkdir -p /tmp/logs media staticfiles

echo "==> [2/5] Aplicando migraciones..."
python manage.py migrate --noinput
MIGRATE_EXIT=$?
if [ $MIGRATE_EXIT -ne 0 ]; then
    echo "CRITICO: migrate falló con código $MIGRATE_EXIT"
    exit 1
fi
echo "Migraciones aplicadas correctamente."

echo "==> [3/5] Cargando datos iniciales..."
python manage.py loaddata control/fixtures/empleados.json 2>/dev/null \
  && echo "Fixtures cargados." \
  || echo "Fixtures ya existentes o advertencia ignorada."

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
