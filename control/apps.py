from django.apps import AppConfig


class ControlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'control'

    def ready(self):
        # Aplicar PRAGMAs WAL en SQLite via señal — la forma correcta
        from django.db.backends.signals import connection_created
        from django.db.models.signals import post_migrate

        def activar_wal(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                cursor = connection.cursor()
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA synchronous=NORMAL;')
                cursor.execute('PRAGMA cache_size=10000;')
                cursor.execute('PRAGMA temp_store=MEMORY;')
                cursor.execute('PRAGMA foreign_keys=ON;')

        def asegurar_departamentos(**kwargs):
            from .services.institutional_seed import ensure_departamentos
            ensure_departamentos()

        connection_created.connect(activar_wal, dispatch_uid='control.sqlite_wal')
        post_migrate.connect(
            asegurar_departamentos,
            sender=self,
            dispatch_uid='control.ensure_departamentos_post_migrate',
        )
        asegurar_departamentos()
