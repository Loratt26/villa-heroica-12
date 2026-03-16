"""
Reportes optimizados. Queries en DB, no en Python.
"""
import csv
import io
from datetime import timedelta, date
from django.db.models import Count, Q
from django.utils import timezone

from ..models import Empleado, RegistroAsistencia, Feriado


def _dias_habiles(fecha_inicio: date, fecha_fin: date) -> list[date]:
    feriados = set(
        Feriado.objects.filter(fecha__range=[fecha_inicio, fecha_fin])
        .values_list('fecha', flat=True)
    )
    dias = []
    d = fecha_inicio
    while d <= fecha_fin:
        if d.weekday() < 5 and d not in feriados:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def resumen_diario(fecha: date, sede_id=None) -> dict:
    qs = RegistroAsistencia.objects.filter(fecha=fecha)
    if sede_id:
        qs = qs.filter(sede_id=sede_id)
    return qs.aggregate(
        total_entradas   = Count('id', filter=Q(hora_entrada__isnull=False)),
        total_salidas    = Count('id', filter=Q(hora_salida__isnull=False)),
        total_tardanzas  = Count('id', filter=Q(tipo_novedad='tardanza')),
        total_salidas_ant = Count('id', filter=Q(tipo_novedad='salida_anticipada')),
    )


def registros_filtrados(empleado_id=None, fecha_inicio=None, fecha_fin=None, sede_id=None):
    """QuerySet base para reportes y CSV. Lazy — no ejecuta hasta iterar."""
    qs = (
        RegistroAsistencia.objects
        .select_related('empleado', 'empleado__departamento', 'autorizado_por')
        .order_by('-fecha', 'empleado__apellido')
    )
    if empleado_id:
        qs = qs.filter(empleado_id=empleado_id)
    if fecha_inicio:
        qs = qs.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__lte=fecha_fin)
    if sede_id:
        qs = qs.filter(sede_id=sede_id)
    return qs


def inasistencias(fecha_inicio: date, fecha_fin: date, sede_id=None) -> list[dict]:
    dias = _dias_habiles(fecha_inicio, fecha_fin)
    if not dias:
        return []

    empleados = Empleado.objects.filter(activo=True)
    if sede_id:
        empleados = empleados.filter(sede_id=sede_id)

    presentes = set(
        RegistroAsistencia.objects
        .filter(fecha__range=[fecha_inicio, fecha_fin])
        .values_list('empleado_id', 'fecha')
    )

    resultado = []
    for emp in empleados:
        for dia in dias:
            if (emp.pk, dia) not in presentes:
                resultado.append({'empleado': emp, 'fecha': dia})
    return resultado


def generar_csv(queryset) -> bytes:
    """
    Retorna bytes UTF-8 con BOM para compatibilidad con Excel en Windows.
    Usar: response.write(generar_csv(qs))
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # BOM UTF-8
    output.write('\ufeff')

    writer.writerow([
        'Fecha', 'Cédula', 'Nombre', 'Apellido', 'Departamento',
        'Hora Entrada', 'Hora Salida', 'Horas Trabajadas',
        'Tipo Novedad', 'Motivo', 'Autorizado Por',
    ])

    for r in queryset.iterator(chunk_size=500):  # no carga todo en memoria
        writer.writerow([
            r.fecha.strftime('%d/%m/%Y'),
            getattr(r.empleado, 'cedula', '') or '',
            r.empleado.nombre,
            r.empleado.apellido,
            r.empleado.departamento.nombre,
            r.hora_entrada.strftime('%H:%M')  if r.hora_entrada else '',
            r.hora_salida.strftime('%H:%M')   if r.hora_salida  else '',
            r.horas_trabajadas(),
            r.get_tipo_novedad_display(),
            r.motivo,
            str(r.autorizado_por) if r.autorizado_por else '',
        ])

    return output.getvalue().encode('utf-8')
