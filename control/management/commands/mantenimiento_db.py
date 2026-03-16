"""
python manage.py mantenimiento_db
Ejecutar semanalmente via cron: 0 2 * * 0 cd /app && python manage.py mantenimiento_db
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'VACUUM + ANALYZE SQLite. No-op en PostgreSQL.'

    def handle(self, *args, **options):
        vendor = connection.vendor  # 'sqlite' o 'postgresql'

        if vendor == 'sqlite':
            with connection.cursor() as c:
                c.execute('PRAGMA wal_checkpoint(TRUNCATE);')
                self.stdout.write('WAL checkpoint OK')
            # VACUUM no puede ejecutarse dentro de una transacción
            # Django abre una por defecto → usar conexión directa
            import sqlite3
            db_path = connection.settings_dict['NAME']
            conn = sqlite3.connect(db_path)
            conn.execute('VACUUM;')
            conn.execute('ANALYZE;')
            conn.close()
            self.stdout.write(self.style.SUCCESS('SQLite: VACUUM + ANALYZE completado.'))

        elif vendor == 'postgresql':
            with connection.cursor() as c:
                c.execute('ANALYZE;')
            self.stdout.write(self.style.SUCCESS('PostgreSQL: ANALYZE completado.'))

        else:
            self.stdout.write(f'Vendor {vendor}: sin acción de mantenimiento definida.')
