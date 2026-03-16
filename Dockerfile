FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crear directorios necesarios
RUN mkdir -p staticfiles media /tmp/logs

# Recolectar estáticos en build time
# DJANGO_SETTINGS_MODULE apunta al settings correcto
RUN python manage.py collectstatic --noinput || echo "collectstatic: advertencia ignorada"

EXPOSE 8000

CMD ["bash", "start.sh"]
