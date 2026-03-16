# 🏫 Control de Asistencia — Colegio Villa Heroica

## ✅ Correr localmente

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata control/fixtures/empleados.json
python manage.py runserver
```
→ http://127.0.0.1:8000  |  usuario: `admin`  |  contraseña: `123456`

---

## 🚂 Desplegar en Railway

### Paso 1 — Subir a GitHub

**IMPORTANTE:** Al descomprimir el ZIP verás estos archivos directamente (sin subcarpeta):
```
manage.py
requirements.txt
Dockerfile
start.sh
asistencia/
control/
...
```

Sube EXACTAMENTE esos archivos a GitHub:

```bash
# Estando en la carpeta donde están manage.py y requirements.txt:
git init
git add .
git commit -m "primer commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/villa-heroica.git
git push -u origin main
```

✅ El repo de GitHub debe mostrar `manage.py` y `requirements.txt` directamente en la raíz, no dentro de una subcarpeta.

### Paso 2 — Crear proyecto en Railway
1. [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Seleccionar el repositorio
3. Railway detecta el `Dockerfile` automáticamente ✅

### Paso 3 — Variables de entorno
En la pestaña **Variables**:

| Variable     | Valor                          |
|--------------|--------------------------------|
| `SECRET_KEY` | `villa-heroica-clave-2024-xyz` |
| `DEBUG`      | `False`                        |

### Paso 4 — URL pública
**Settings → Networking → Generate Domain**

---

## 🔑 Credenciales
| Campo      | Valor                |
|------------|----------------------|
| Usuario    | `admin`              |
| Contraseña | `123456`             |
