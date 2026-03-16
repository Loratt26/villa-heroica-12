from collections import defaultdict
from datetime import timedelta
import csv
import io

from django.db.models import Case, F, IntegerField, Q, Value, When

from ..models import AlertaTardanza, RegistroAsistencia, SystemSettings


def inicio_semana(fecha):
    return fecha - timedelta(days=fecha.weekday())


def fin_semana(fecha):
    monday = inicio_semana(fecha)
    return monday + timedelta(days=6)


def get_system_settings():
    return SystemSettings.load()


def get_tardanza_limit():
    return get_system_settings().tardanzas_alerta_limite


def tardanza_q(prefix=''):
    return (
        Q(**{f'{prefix}tipo_novedad': 'tardanza'}) |
        (
            Q(**{f'{prefix}hora_entrada__isnull': False}) &
            Q(**{f'{prefix}horario_entrada_esperado__isnull': False}) &
            Q(**{f'{prefix}hora_entrada__gt': F(f'{prefix}horario_entrada_esperado')})
        )
    )


def tardanza_case(prefix=''):
    return Case(
        When(tardanza_q(prefix), then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )


def annotate_tardanza_flag(queryset, field_name='es_tardanza_alerta'):
    return queryset.annotate(**{field_name: tardanza_case()})


def tardanza_queryset(queryset=None):
    base_queryset = queryset if queryset is not None else RegistroAsistencia.objects.all()
    return annotate_tardanza_flag(base_queryset).filter(es_tardanza_alerta=1)


def sync_tardanza_alert_for_employee_week(empleado, fecha):
    semana = inicio_semana(fecha)
    limite = get_tardanza_limit()
    cantidad = tardanza_queryset(
        RegistroAsistencia.objects.filter(
            empleado=empleado,
            fecha__range=[semana, semana + timedelta(days=6)],
        )
    ).count()

    alerta = AlertaTardanza.objects.filter(empleado=empleado, semana=semana).first()

    if cantidad > limite:
        if alerta is None:
            return AlertaTardanza.objects.create(
                empleado=empleado,
                semana=semana,
                cantidad_tardanzas=cantidad,
                resuelta=False,
            )

        reopen = cantidad > alerta.cantidad_tardanzas
        alerta.cantidad_tardanzas = cantidad
        if reopen:
            alerta.resuelta = False
        alerta.save(update_fields=['cantidad_tardanzas', 'resuelta', 'updated_at'])
        return alerta

    if alerta is not None:
        alerta.cantidad_tardanzas = cantidad
        alerta.resuelta = True
        alerta.save(update_fields=['cantidad_tardanzas', 'resuelta', 'updated_at'])
    return alerta


def refresh_all_tardanza_alerts():
    limite = get_tardanza_limit()
    tardanzas = (
        tardanza_queryset()
        .select_related('empleado')
        .only('empleado_id', 'fecha')
    )

    counts = defaultdict(int)
    for registro in tardanzas.iterator(chunk_size=500):
        counts[(registro.empleado_id, inicio_semana(registro.fecha))] += 1

    existentes = {
        (alerta.empleado_id, alerta.semana): alerta
        for alerta in AlertaTardanza.objects.all()
    }
    touched = set()

    for key, cantidad in counts.items():
        touched.add(key)
        alerta = existentes.get(key)

        if cantidad > limite:
            if alerta is None:
                AlertaTardanza.objects.create(
                    empleado_id=key[0],
                    semana=key[1],
                    cantidad_tardanzas=cantidad,
                    resuelta=False,
                )
            else:
                reopen = cantidad > alerta.cantidad_tardanzas
                alerta.cantidad_tardanzas = cantidad
                if reopen:
                    alerta.resuelta = False
                alerta.save(update_fields=['cantidad_tardanzas', 'resuelta', 'updated_at'])
        elif alerta is not None:
            alerta.cantidad_tardanzas = cantidad
            alerta.resuelta = True
            alerta.save(update_fields=['cantidad_tardanzas', 'resuelta', 'updated_at'])

    for key, alerta in existentes.items():
        if key not in touched:
            if alerta.cantidad_tardanzas != 0 or not alerta.resuelta:
                alerta.cantidad_tardanzas = 0
                alerta.resuelta = True
                alerta.save(update_fields=['cantidad_tardanzas', 'resuelta', 'updated_at'])


def registros_tardanza_de_alerta(alerta):
    return tardanza_queryset(
        RegistroAsistencia.objects.filter(
            empleado=alerta.empleado,
            fecha__range=[alerta.semana, alerta.semana + timedelta(days=6)],
        )
    ).select_related('empleado', 'empleado__departamento', 'autorizado_por').order_by('-fecha', '-hora_entrada')


def generar_csv_tardanzas(alerta, queryset) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    output.write('\ufeff')
    writer.writerow([
        'Semana',
        'Fecha',
        'Cedula',
        'Empleado',
        'Departamento',
        'Hora entrada',
        'Hora esperada',
        'Minutos tarde',
        'Motivo',
        'Autorizado por',
    ])

    for registro in queryset.iterator(chunk_size=500):
        writer.writerow([
            alerta.semana.strftime('%d/%m/%Y'),
            registro.fecha.strftime('%d/%m/%Y'),
            registro.empleado.cedula or '',
            str(registro.empleado),
            registro.empleado.departamento.nombre,
            registro.hora_entrada.strftime('%H:%M') if registro.hora_entrada else '',
            registro.horario_entrada_esperado.strftime('%H:%M') if registro.horario_entrada_esperado else '',
            registro.minutos_tardanza(),
            registro.motivo,
            str(registro.autorizado_por) if registro.autorizado_por else '',
        ])

    return output.getvalue().encode('utf-8')
