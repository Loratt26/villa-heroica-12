"""
python manage.py verificar_db
Detecta registros corruptos antes de despliegue o auditoría.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone


class Command(BaseCommand):
    help = 'Detecta registros de asistencia con datos inconsistentes.'

    def handle(self, *args, **options):
        from control.models import RegistroAsistencia, Empleado

        errores = 0

        # 1. Salida sin entrada
        qs = RegistroAsistencia.objects.filter(
            hora_entrada__isnull=True,
            hora_salida__isnull=False,
        )
        if qs.exists():
            self.stdout.write(self.style.ERROR(f'[{qs.count()}] registros con salida sin entrada:'))
            for r in qs[:10]:
                self.stdout.write(f'  ID={r.pk} {r.empleado} {r.fecha}')
            errores += qs.count()

        # 2. Salida anterior a entrada (imposible físicamente)
        from datetime import datetime, date as date_type
        inconsistentes = []
        for r in RegistroAsistencia.objects.filter(
            hora_entrada__isnull=False,
            hora_salida__isnull=False,
        ).iterator(chunk_size=500):
            entrada = datetime.combine(date_type.today(), r.hora_entrada)
            salida  = datetime.combine(date_type.today(), r.hora_salida)
            if salida <= entrada:
                inconsistentes.append(r.pk)

        if inconsistentes:
            self.stdout.write(self.style.ERROR(
                f'[{len(inconsistentes)}] registros con salida ≤ entrada: IDs={inconsistentes[:10]}'
            ))
            errores += len(inconsistentes)

        # 3. Empleados sin cédula (no pueden usar kiosco)
        sin_cedula = Empleado.objects.filter(activo=True, cedula__isnull=True).count()
        if sin_cedula:
            self.stdout.write(self.style.WARNING(
                f'[{sin_cedula}] empleados activos sin cédula registrada.'
            ))

        # 4. Registros con tipo_novedad=tardanza pero sin motivo
        sin_motivo = RegistroAsistencia.objects.filter(
            tipo_novedad__in=['tardanza', 'salida_anticipada'],
            motivo='',
        ).count()
        if sin_motivo:
            self.stdout.write(self.style.WARNING(
                f'[{sin_motivo}] novedades sin motivo registrado.'
            ))

        # Resumen
        if errores == 0 and sin_cedula == 0:
            self.stdout.write(self.style.SUCCESS('Base de datos: sin inconsistencias detectadas. ✅'))
        else:
            self.stdout.write(self.style.WARNING(f'Total problemas: {errores} errores, revisar.'))
