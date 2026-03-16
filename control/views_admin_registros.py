"""
CRUD admin de registros de asistencia.
Vistas separadas — solo staff autenticado.
No accesibles desde kiosco.
"""
import logging
from datetime import time as time_type

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import RegistroAsistencia, Empleado, AuditLog, EstadoRegistro
from .services.admin_registros import editar_registro, eliminar_registro
from .services.asistencia import _get_ip

logger = logging.getLogger('control.asistencia')


def _es_staff(user):
    return user.is_staff or user.is_superuser


def _empleado_del_request(request) -> Empleado | None:
    """Obtiene el Empleado vinculado al usuario admin logueado, si existe."""
    try:
        return request.user.empleado
    except Exception:
        return None


# ── Lista de registros (panel admin) ──────────────────────────────────────────

@login_required
@user_passes_test(_es_staff, login_url='/')
def admin_lista_registros(request):
    fecha_str = request.GET.get('fecha', str(timezone.localdate()))
    try:
        from datetime import date
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = timezone.localdate()

    registros = (
        RegistroAsistencia.objects
        .filter(fecha=fecha)
        .select_related('empleado', 'empleado__departamento', 'autorizado_por')
        .order_by('empleado__apellido', 'empleado__nombre')
    )

    return render(request, 'control/admin/registros_lista.html', {
        'registros': registros,
        'fecha':     fecha,
    })


# ── Editar registro ───────────────────────────────────────────────────────────

@login_required
@user_passes_test(_es_staff, login_url='/')
def admin_editar_registro(request, pk):
    registro = get_object_or_404(
        RegistroAsistencia.objects.select_related('empleado'),
        pk=pk
    )

    if registro.estado == EstadoRegistro.CERRADO:
        messages.error(request, 'Este registro está cerrado y no puede editarse.')
        return redirect('admin_lista_registros')

    if request.method == 'POST':
        hora_entrada_str = request.POST.get('hora_entrada', '').strip()
        hora_salida_str  = request.POST.get('hora_salida', '').strip()
        motivo           = request.POST.get('motivo', '').strip()
        tipo_novedad     = request.POST.get('tipo_novedad', '').strip() or None

        def parse_time(s):
            if not s:
                return None
            try:
                h, m = s.split(':')
                return time_type(int(h), int(m))
            except Exception:
                return None

        hora_entrada = parse_time(hora_entrada_str) if hora_entrada_str else None
        hora_salida  = parse_time(hora_salida_str)  if hora_salida_str  else None

        resultado = editar_registro(
            registro.pk,
            hora_entrada  = hora_entrada,
            hora_salida   = hora_salida,
            motivo        = motivo if motivo else None,
            tipo_novedad  = tipo_novedad,
            editor_empleado = _empleado_del_request(request),
            ip            = _get_ip(request),
        )

        if resultado['ok']:
            messages.success(request, f'Registro de {registro.empleado} actualizado.')
            logger.info(
                'admin_editar_registro pk=%s por user=%s',
                pk, request.user.username
            )
            return redirect('admin_lista_registros')

        errores = {
            'HORA_INVALIDA':    'La hora de salida debe ser posterior a la entrada.',
            'JORNADA_EXCESIVA': f'La jornada no puede superar 16 horas.',
            'NOVEDAD_INVALIDA': 'Tipo de novedad no válido.',
            'REGISTRO_CERRADO': 'El registro está cerrado.',
            'ESTADO_INVALIDO':  'Transición de estado no permitida.',
        }
        messages.error(request, errores.get(resultado['codigo'], resultado['codigo']))

    return render(request, 'control/admin/registro_editar.html', {
        'registro': registro,
        'novedades': RegistroAsistencia.NOVEDAD,
    })


# ── Eliminar registro ─────────────────────────────────────────────────────────

@login_required
@user_passes_test(_es_staff, login_url='/')
def admin_eliminar_registro(request, pk):
    registro = get_object_or_404(
        RegistroAsistencia.objects.select_related('empleado'),
        pk=pk
    )

    if registro.estado == EstadoRegistro.CERRADO:
        messages.error(request, 'Este registro está cerrado y no puede eliminarse.')
        return redirect('admin_lista_registros')

    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()

        resultado = eliminar_registro(
            registro.pk,
            editor_empleado   = _empleado_del_request(request),
            ip                = _get_ip(request),
            motivo_eliminacion = motivo,
        )

        if resultado['ok']:
            messages.success(request, f'Registro eliminado correctamente.')
            logger.info(
                'admin_eliminar_registro pk=%s por user=%s motivo=%s',
                pk, request.user.username, motivo
            )
            return redirect('admin_lista_registros')

        messages.error(request, 'No se pudo eliminar el registro.')

    return render(request, 'control/admin/registro_eliminar.html', {
        'registro': registro,
    })


# ── Log de auditoría ──────────────────────────────────────────────────────────

@login_required
@user_passes_test(_es_staff, login_url='/')
def admin_audit_log(request):
    logs = (
        AuditLog.objects
        .select_related('empleado', 'realizado_por')
        .order_by('-timestamp')[:200]
    )
    return render(request, 'control/admin/audit_log.html', {'logs': logs})
