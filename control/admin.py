from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from .models import (
    Departamento, Sede, Feriado, Empleado,
    RegistroAsistencia, AuditLog, KioscoToken, AlertaTardanza, SystemSettings,
)

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'activa')


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display  = ('fecha', 'descripcion')
    ordering      = ('-fecha',)
    date_hierarchy = 'fecha'


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display  = ('apellido', 'nombre', 'cedula', 'cargo', 'departamento', 'activo')
    list_filter   = ('departamento', 'activo')
    search_fields = ('nombre', 'apellido', 'cedula')


@admin.register(RegistroAsistencia)
class RegistroAdmin(admin.ModelAdmin):
    list_display    = ('empleado', 'fecha', 'hora_entrada', 'hora_salida', 'tipo_novedad', 'estado')
    list_filter     = ('fecha', 'tipo_novedad', 'estado', 'empleado__departamento')
    search_fields   = ('empleado__nombre', 'empleado__apellido', 'empleado__cedula')
    date_hierarchy  = 'fecha'
    readonly_fields = ('created_at', 'updated_at', 'ip_kiosco',
                       'horario_entrada_esperado', 'horario_salida_esperado', 'estado')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ('accion', 'empleado', 'realizado_por', 'timestamp', 'ip_address')
    list_filter   = ('accion',)
    search_fields = ('empleado__nombre', 'empleado__apellido')
    date_hierarchy = 'timestamp'
    readonly_fields = ('accion', 'empleado', 'realizado_por', 'timestamp',
                       'ip_address', 'datos_antes', 'datos_despues', 'metadata')

    def has_add_permission(self, request):
        return False  # AuditLog: solo lectura en admin

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(KioscoToken)
class KioscoTokenAdmin(admin.ModelAdmin):
    list_display = ('empleado', 'accion', 'usado', 'creado_at', 'expira_at')
    readonly_fields = ('token', 'creado_at')


@admin.register(AlertaTardanza)
class AlertaTardanzaAdmin(admin.ModelAdmin):
    list_display = ('empleado', 'semana', 'cantidad_tardanzas', 'resuelta', 'updated_at')
    list_filter = ('resuelta', 'semana', 'empleado__departamento')
    search_fields = ('empleado__nombre', 'empleado__apellido', 'empleado__cedula')
    ordering = ('resuelta', '-cantidad_tardanzas', '-semana')


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ('tardanzas_alerta_limite', 'updated_at')

    def has_add_permission(self, request):
        if SystemSettings.objects.exists():
            return False
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)
