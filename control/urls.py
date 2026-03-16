from django.urls import path
from . import views
from . import views_admin_registros as admin_views

urlpatterns = [
    # ── Dashboard ──────────────────────────────────────────────────
    path('', views.dashboard, name='dashboard'),

    # ── Kiosco (público) ───────────────────────────────────────────
    path('kiosco/',                              views.kiosco,            name='kiosco'),
    path('kiosco/cedula/',                       views.kiosco_cedula,     name='kiosco_cedula'),
    path('kiosco/marcar/',                       views.kiosco_marcar,     name='kiosco_marcar'),
    path('kiosco/bienvenida/<int:registro_id>/', views.kiosco_bienvenida, name='kiosco_bienvenida'),
    path('kiosco/api/cedula/',                   views.api_buscar_cedula, name='api_buscar_cedula'),

    # ── Marcaje admin ──────────────────────────────────────────────
    path('marcaje/', views.marcaje, name='marcaje'),

    # ── Empleados ──────────────────────────────────────────────────
    path('empleados/',                 views.lista_empleados, name='lista_empleados'),
    path('empleados/nuevo/',           views.crear_empleado,  name='crear_empleado'),
    path('empleados/<int:pk>/editar/', views.editar_empleado, name='editar_empleado'),
    path('empleados/<int:pk>/',        views.ver_empleado,    name='ver_empleado'),

    # ── Reportes ───────────────────────────────────────────────────
    path('reportes/',          views.reportes,     name='reportes'),
    path('reportes/exportar/', views.exportar_csv, name='exportar_csv'),
    path('alertas/',           views.alertas_tardanza,          name='alertas_tardanza'),
    path('alertas/<int:pk>/',  views.alerta_tardanza_detalle,   name='alerta_tardanza_detalle'),
    path('alertas/<int:pk>/exportar/', views.alerta_tardanza_exportar, name='alerta_tardanza_exportar'),
    path('configuracion/',     views.configuracion_sistema,     name='configuracion_sistema'),

    # ── Usuarios ───────────────────────────────────────────────────
    path('usuarios/',                    views.lista_usuarios,           name='lista_usuarios'),
    path('usuarios/nuevo/',              views.crear_usuario,            name='crear_usuario'),
    path('usuarios/<int:pk>/editar/',    views.editar_usuario,           name='editar_usuario'),
    path('usuarios/<int:pk>/password/',  views.cambiar_password_usuario, name='cambiar_password'),
    path('usuarios/<int:pk>/eliminar/',  views.eliminar_usuario,         name='eliminar_usuario'),

    # ── Admin registros (solo staff) ────────────────────────────────
    path('admin-registros/',
         admin_views.admin_lista_registros, name='admin_lista_registros'),
    path('admin-registros/<int:pk>/editar/',
         admin_views.admin_editar_registro, name='admin_editar_registro'),
    path('admin-registros/<int:pk>/eliminar/',
         admin_views.admin_eliminar_registro, name='admin_eliminar_registro'),
    path('admin-registros/auditoria/',
         admin_views.admin_audit_log, name='admin_audit_log'),
]
