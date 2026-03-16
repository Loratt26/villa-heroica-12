import logging
import re
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect

from .forms import (CambiarPasswordForm, CrearUsuarioForm, EditarUsuarioForm,
                    EmpleadoForm, ReporteForm, SystemSettingsForm)
from .models import Empleado, RegistroAsistencia, Departamento, AlertaTardanza, SystemSettings
from .validators import normalizar_cedula, cedula_es_valida
from .services.autofill_cache import buscar_empleado_cached, check_rate_limit
from .services.kiosco_token import emitir_token, consumir_token
from .services.asistencia import (evaluar_entrada, evaluar_salida,
                                   registrar_entrada, registrar_salida,
                                   _get_ip)
from .services.reportes import (generar_csv, inasistencias,
                                  registros_filtrados, resumen_diario)
from .services.tardanzas import (
    fin_semana,
    generar_csv_tardanzas,
    refresh_all_tardanza_alerts,
    registros_tardanza_de_alerta,
    sync_tardanza_alert_for_employee_week,
)

logger = logging.getLogger('control.asistencia')


def es_admin(user):
    return user.is_staff or user.is_superuser


def es_superuser(user):
    return user.is_superuser


def _safe_media_url(request, field_file):
    if not field_file or not getattr(field_file, 'name', ''):
        return None
    try:
        return request.build_absolute_uri(field_file.url)
    except Exception:
        return None


# Mapa completo de códigos → mensajes de usuario
_MENSAJES_ERROR = {
    'ENTRADA_DUPLICADA':      'Ya tienes entrada registrada hoy.',
    'SALIDA_DUPLICADA':       'Ya tienes salida registrada hoy.',
    'SIN_ENTRADA':            'No puedes registrar salida sin haber marcado entrada hoy.',
    'EMPLEADO_INACTIVO':      'Tu cuenta está inactiva. Contacta a administración.',
    'AUTORIZACION_REQUERIDA': 'Esta salida anticipada requiere autorización.',
    'AUTORIZACION_INVALIDA':  'El autorizador seleccionado no es válido.',
    'MOTIVO_REQUERIDO':       'Debes escribir el motivo.',
    'HORA_INVALIDA':          'La hora de salida no puede ser anterior o igual a la entrada.',
    'DOBLE_SUBMIT':           'Solicitud duplicada. Espera un momento e intenta de nuevo.',
    'ERROR_DB':               'Error temporal del sistema. Por favor intenta de nuevo.',
}


# ── Dashboard ─────────────────────────────────────────────────────────────────

def dashboard(request):
    if not request.user.is_authenticated:
        return render(request, 'control/landing.html')

    refresh_all_tardanza_alerts()
    hoy     = timezone.localdate()
    resumen = resumen_diario(hoy)
    total   = Empleado.objects.filter(activo=True).count()
    ultimos = (
        RegistroAsistencia.objects
        .filter(fecha=hoy)
        .select_related('empleado')
        .order_by('-hora_entrada')[:8]
    )
    alertas_activas = AlertaTardanza.objects.filter(resuelta=False).count()
    return render(request, 'control/dashboard.html', {
        'hoy':             hoy,
        'total_empleados': total,
        'con_entrada':     resumen['total_entradas'],
        'presentes':       max(resumen['total_entradas'] - resumen['total_salidas'], 0),
        'ausentes':        max(total - resumen['total_entradas'], 0),
        'con_salida':      resumen['total_salidas'],
        'total_tardanzas': resumen['total_tardanzas'],
        'alertas_activas': alertas_activas,
        'ultimos_registros': ultimos,
    })


# ── Kiosco (sin login) ────────────────────────────────────────────────────────

def kiosco(request):
    from django.conf import settings
    return render(request, 'control/kiosco/cedula.html', {
        'accion_inicial': request.GET.get('accion', 'entrada'),
        'idle_segundos': getattr(settings, 'KIOSCO_IDLE_SEGUNDOS', 30),
    })


@require_GET
def kiosco_cedula(request):
    accion = request.GET.get('accion', 'entrada')
    if accion not in ('entrada', 'salida'):
        accion = 'entrada'
    from django.conf import settings
    return render(request, 'control/kiosco/cedula.html', {
        'accion_inicial': accion,
        'idle_segundos': getattr(settings, 'KIOSCO_IDLE_SEGUNDOS', 30),
    })


@require_GET
def api_buscar_cedula(request):
    """
    GET /kiosco/api/cedula/?q=V-27421625
    Respuesta JSON con datos del empleado y evaluación de novedades.
    No modifica DB.
    """
    raw = request.GET.get('q', '').strip()
    if not raw:
        return JsonResponse({'encontrado': False, 'error': 'vacio'})

    if not cedula_es_valida(raw):
        return JsonResponse({'encontrado': False, 'error': 'formato_invalido'})

    cedula = normalizar_cedula(raw)

    try:
        emp = (
            Empleado.objects
            .select_related('departamento')
            .get(cedula=cedula)
        )
    except Empleado.DoesNotExist:
        return JsonResponse({'encontrado': False, 'error': 'no_registrado'})

    # Diferenciar inactivo de no registrado para dar mensaje preciso
    if not emp.activo:
        return JsonResponse({'encontrado': False, 'error': 'inactivo'})

    hoy     = timezone.localdate()
    ahora   = timezone.localtime().time()
    reg_hoy = RegistroAsistencia.objects.filter(empleado=emp, fecha=hoy).first()

    eval_entrada = evaluar_entrada(emp, ahora)
    eval_salida  = evaluar_salida(emp, ahora)

    return JsonResponse({
        'encontrado':      True,
        'id':              emp.pk,
        'nombre':          emp.nombre,
        'apellido':        emp.apellido,
        'cargo':           emp.cargo,
        'departamento':    emp.departamento.nombre,
        'foto_url':        _safe_media_url(request, emp.foto),
        'tiene_entrada':   bool(reg_hoy and reg_hoy.hora_entrada),
        'tiene_salida':    bool(reg_hoy and reg_hoy.hora_salida),
        'hora_entrada_hoy': (
            reg_hoy.hora_entrada.strftime('%H:%M')
            if reg_hoy and reg_hoy.hora_entrada else None
        ),
        'evaluacion_entrada': eval_entrada,
        'evaluacion_salida':  eval_salida,
    })


@csrf_protect
@require_POST
def kiosco_marcar(request):
    """
    POST /kiosco/marcar/
    Procesa marcaje. Redirige a bienvenida si ok, a error si falla.
    """
    empleado_id       = request.POST.get('empleado_id', '').strip()
    accion            = request.POST.get('accion', '').strip()
    motivo            = request.POST.get('motivo', '').strip()
    autorizado_por_id = request.POST.get('autorizado_por_id', '').strip() or None

    # Validaciones de entrada antes de tocar DB
    if accion not in ('entrada', 'salida'):
        logger.warning('kiosco_marcar: accion inválida "%s"', accion)
        return redirect('kiosco')

    try:
        empleado_id_int = int(empleado_id)
    except (ValueError, TypeError):
        logger.warning('kiosco_marcar: empleado_id inválido "%s"', empleado_id)
        return redirect('kiosco')

    try:
        empleado = Empleado.objects.select_related('departamento').get(pk=empleado_id_int)
    except Empleado.DoesNotExist:
        logger.warning('kiosco_marcar: empleado %s no existe', empleado_id)
        return redirect('kiosco')

    ahora = timezone.localtime().time()
    ip    = _get_ip(request)

    if accion == 'entrada':
        resultado = registrar_entrada(empleado, ahora, motivo=motivo, ip=ip)
    else:
        resultado = registrar_salida(
            empleado, ahora,
            motivo=motivo,
            autorizado_por_id=int(autorizado_por_id) if autorizado_por_id else None,
            ip=ip,
        )

    if resultado['ok']:
        logger.info(
            'kiosco_marcar: %s %s %s %s',
            accion, empleado.cedula or empleado_id, ahora, ip
        )
        return redirect('kiosco_bienvenida', registro_id=resultado['registro'].pk)

    # Fallo — loggear y mostrar pantalla de error amigable
    codigo  = resultado.get('codigo', 'DESCONOCIDO')
    mensaje = _MENSAJES_ERROR.get(codigo, f'Error inesperado ({codigo}).')

    logger.warning(
        'kiosco_marcar FAIL: %s %s %s codigo=%s',
        accion, empleado.cedula or empleado_id, ahora, codigo
    )

    return render(request, 'control/kiosco/error.html', {
        'mensaje': mensaje,
        'codigo':  codigo,
    })


def kiosco_bienvenida(request, registro_id):
    from django.conf import settings
    registro = get_object_or_404(
        RegistroAsistencia.objects.select_related('empleado'),
        pk=registro_id,
    )
    ahora = timezone.localtime()
    hora  = ahora.hour
    dia   = ahora.weekday()

    saludo = (
        'Buenos días'   if hora < 12 else
        'Buenas tardes' if hora < 18 else
        'Buenas noches'
    )
    mensajes_dia = {
        0: 'Excelente inicio de semana.',
        1: 'Sigue adelante, vas muy bien.',
        2: 'Ya es miércoles — mitad de semana lograda.',
        3: 'Un día más de dedicación y compromiso.',
        4: '¡Buen trabajo esta semana! Que disfrutes tu fin de semana.',
        5: 'Gracias por tu compromiso hoy sábado.',
        6: 'Gracias por tu dedicación.',
    }
    hora_display = registro.hora_salida or registro.hora_entrada

    return render(request, 'control/kiosco/bienvenida.html', {
        'registro':    registro,
        'saludo':      saludo,
        'mensaje_dia': mensajes_dia[dia],
        'accion':      'Entrada' if registro.hora_entrada and not registro.hora_salida else 'Salida',
        'hora_display': hora_display.strftime('%I:%M %p') if hora_display else '',
        'es_tardanza':  registro.tipo_novedad == 'tardanza',
        'segundos':     getattr(settings, 'KIOSCO_BIENVENIDA_SEGUNDOS', 4),
    })


# ── Marcaje admin ─────────────────────────────────────────────────────────────

@login_required
def marcaje(request):
    hoy      = timezone.localdate()
    ahora    = timezone.localtime().time()
    empleados = Empleado.objects.filter(activo=True).order_by('apellido', 'nombre')

    if request.method == 'POST':
        try:
            empleado = Empleado.objects.get(pk=int(request.POST.get('empleado_id', 0)))
        except (Empleado.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Empleado no válido.')
            return redirect('marcaje')

        accion = request.POST.get('accion')
        motivo = request.POST.get('motivo', '').strip()

        if accion == 'entrada':
            r = registrar_entrada(empleado, ahora, motivo=motivo, ip=_get_ip(request))
        elif accion == 'salida':
            r = registrar_salida(empleado, ahora, motivo=motivo, ip=_get_ip(request))
        else:
            messages.error(request, 'Acción no válida.')
            return redirect('marcaje')

        if r['ok']:
            hora_str = ahora.strftime('%H:%M')
            messages.success(request, f'✅ {accion.title()} registrada para {empleado} a las {hora_str}.')
        else:
            msg = _MENSAJES_ERROR.get(r['codigo'], r['codigo'])
            messages.warning(request, f'{empleado}: {msg}')

        return redirect('marcaje')

    registros_hoy = (
        RegistroAsistencia.objects
        .filter(fecha=hoy)
        .select_related('empleado')
        .order_by('-hora_entrada')
    )
    return render(request, 'control/marcaje.html', {
        'empleados':     empleados,
        'hoy':           hoy,
        'ahora':         ahora,
        'registros_hoy': registros_hoy,
    })


# ── Empleados ─────────────────────────────────────────────────────────────────

@login_required
def lista_empleados(request):
    qs    = Empleado.objects.select_related('departamento').order_by('apellido', 'nombre')
    depts = Departamento.objects.all()

    dept_id = request.GET.get('departamento')
    buscar  = request.GET.get('buscar', '').strip()

    if dept_id:
        qs = qs.filter(departamento_id=dept_id)
    if buscar:
        qs = (
            qs.filter(nombre__icontains=buscar)   |
            qs.filter(apellido__icontains=buscar) |
            qs.filter(cedula__icontains=buscar)
        )

    return render(request, 'control/empleados_lista.html', {
        'empleados':         qs.distinct(),
        'departamentos':     depts,
        'dept_seleccionado': dept_id,
        'buscar':            buscar,
    })


@login_required
def crear_empleado(request):
    if request.method == 'POST':
        form = EmpleadoForm(request.POST, request.FILES)
        if form.is_valid():
            emp = form.save()
            messages.success(request, f'Empleado {emp} creado exitosamente.')
            return redirect('lista_empleados')
    else:
        form = EmpleadoForm()
    return render(request, 'control/empleado_form.html', {'form': form, 'accion': 'Crear'})


@login_required
def editar_empleado(request, pk):
    empleado = get_object_or_404(Empleado, pk=pk)
    if request.method == 'POST':
        form = EmpleadoForm(request.POST, request.FILES, instance=empleado)
        if form.is_valid():
            form.save()
            messages.success(request, f'Empleado {empleado} actualizado.')
            return redirect('lista_empleados')
    else:
        form = EmpleadoForm(instance=empleado)
    return render(request, 'control/empleado_form.html', {
        'form': form, 'empleado': empleado, 'accion': 'Editar'
    })


@login_required
def ver_empleado(request, pk):
    empleado  = get_object_or_404(Empleado, pk=pk)
    registros = RegistroAsistencia.objects.filter(empleado=empleado).order_by('-fecha')[:30]
    return render(request, 'control/empleado_detalle.html', {
        'empleado': empleado, 'registros': registros
    })


# ── Reportes ──────────────────────────────────────────────────────────────────

@login_required
def reportes(request):
    form      = ReporteForm(request.GET or None)
    registros = None
    ausencias = []
    total     = 0

    if form.is_valid():
        emp_id = form.cleaned_data.get('empleado')
        fi     = form.cleaned_data.get('fecha_inicio')
        ff     = form.cleaned_data.get('fecha_fin')
        tipo   = form.cleaned_data.get('tipo_reporte', 'asistencias')

        if tipo == 'inasistencias' and fi and ff:
            ausencias = inasistencias(fi, ff)
        else:
            qs        = registros_filtrados(
                empleado_id  = emp_id.pk if emp_id else None,
                fecha_inicio = fi,
                fecha_fin    = ff,
            )
            registros = qs[:200]
            total     = qs.count()

    return render(request, 'control/reportes.html', {
        'form':      form,
        'registros': registros,
        'ausencias': ausencias,
        'total':     total,
    })


@login_required
def exportar_csv(request):
    data = request.GET.copy()
    hoy = timezone.localdate().isoformat()
    if not data.get('fecha_inicio'):
        data['fecha_inicio'] = hoy
    if not data.get('fecha_fin'):
        data['fecha_fin'] = hoy
    if not data.get('tipo_reporte'):
        data['tipo_reporte'] = 'asistencias'

    form = ReporteForm(data)
    if not form.is_valid():
        messages.error(request, 'No se pudo exportar con los filtros actuales.')
        return redirect('reportes')

    emp_id = form.cleaned_data.get('empleado')
    fi     = form.cleaned_data.get('fecha_inicio')
    ff     = form.cleaned_data.get('fecha_fin')

    qs = registros_filtrados(
        empleado_id  = emp_id.pk if emp_id else None,
        fecha_inicio = fi,
        fecha_fin    = ff,
    )

    nombre_archivo = f'asistencia_{date.today()}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    response.write(generar_csv(qs))

    logger.info('exportar_csv: usuario=%s filtros=%s', request.user, request.GET)
    return response


@login_required
@user_passes_test(es_admin, login_url='/')
def alertas_tardanza(request):
    refresh_all_tardanza_alerts()
    alertas = (
        AlertaTardanza.objects
        .select_related('empleado', 'empleado__departamento')
        .order_by('resuelta', '-cantidad_tardanzas', '-semana', 'empleado__apellido', 'empleado__nombre')
    )
    return render(request, 'control/alertas_lista.html', {
        'alertas': alertas,
    })


@login_required
@user_passes_test(es_admin, login_url='/')
def alerta_tardanza_detalle(request, pk):
    alerta = get_object_or_404(
        AlertaTardanza.objects.select_related('empleado', 'empleado__departamento'),
        pk=pk,
    )
    sync_tardanza_alert_for_employee_week(alerta.empleado, alerta.semana)
    alerta.refresh_from_db()

    if request.method == 'POST':
        alerta.resuelta = True
        alerta.save(update_fields=['resuelta', 'updated_at'])
        messages.success(request, 'Alerta marcada como resuelta.')
        return redirect('alerta_tardanza_detalle', pk=alerta.pk)

    registros = registros_tardanza_de_alerta(alerta)
    return render(request, 'control/alerta_detalle.html', {
        'alerta': alerta,
        'registros': registros,
        'semana_fin': fin_semana(alerta.semana),
    })


@login_required
@user_passes_test(es_admin, login_url='/')
def alerta_tardanza_exportar(request, pk):
    alerta = get_object_or_404(
        AlertaTardanza.objects.select_related('empleado', 'empleado__departamento'),
        pk=pk,
    )
    registros = registros_tardanza_de_alerta(alerta)
    nombre_archivo = f'tardanzas_{alerta.empleado.cedula or alerta.empleado.pk}_{alerta.semana}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    response.write(generar_csv_tardanzas(alerta, registros))
    return response


@login_required
@user_passes_test(es_superuser, login_url='/')
def configuracion_sistema(request):
    settings_obj = SystemSettings.load()
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            refresh_all_tardanza_alerts()
            messages.success(request, 'Configuracion del sistema actualizada.')
            return redirect('configuracion_sistema')
    else:
        form = SystemSettingsForm(instance=settings_obj)

    return render(request, 'control/configuracion_sistema.html', {
        'form': form,
        'settings_obj': settings_obj,
    })


# ── Usuarios ──────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(es_admin, login_url='/')
def lista_usuarios(request):
    return render(request, 'control/usuarios_lista.html', {
        'usuarios': User.objects.all().order_by('username')
    })


@login_required
@user_passes_test(es_admin, login_url='/')
def crear_usuario(request):
    if request.method == 'POST':
        form = CrearUsuarioForm(request.POST)
        if form.is_valid():
            u = form.save()
            messages.success(request, f"Usuario '{u.username}' creado.")
            return redirect('lista_usuarios')
    else:
        form = CrearUsuarioForm()
    return render(request, 'control/usuario_form.html', {'form': form, 'accion': 'Crear'})


@login_required
@user_passes_test(es_admin, login_url='/')
def editar_usuario(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, f"Usuario '{usuario.username}' actualizado.")
            return redirect('lista_usuarios')
    else:
        form = EditarUsuarioForm(instance=usuario)
    return render(request, 'control/usuario_form.html', {
        'form': form, 'accion': 'Editar', 'usuario': usuario
    })


@login_required
@user_passes_test(es_admin, login_url='/')
def cambiar_password_usuario(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = CambiarPasswordForm(request.POST)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['password1'])
            usuario.save()
            messages.success(request, f"Contraseña de '{usuario.username}' actualizada.")
            return redirect('lista_usuarios')
    else:
        form = CambiarPasswordForm()
    return render(request, 'control/usuario_password.html', {
        'form': form, 'usuario': usuario
    })


@login_required
@user_passes_test(es_admin, login_url='/')
def eliminar_usuario(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if usuario == request.user:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')
        return redirect('lista_usuarios')
    if request.method == 'POST':
        nombre = usuario.username
        usuario.delete()
        messages.success(request, f"Usuario '{nombre}' eliminado.")
        return redirect('lista_usuarios')
    return render(request, 'control/usuario_confirmar_eliminar.html', {'usuario': usuario})
