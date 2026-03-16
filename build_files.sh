#!/bin/bash
echo "==> Instalando dependencias..."
pip install -r requirements.txt

echo "==> Recolectando archivos estáticos..."
python manage.py collectstatic --noinput --clear

echo "==> Build completado."
