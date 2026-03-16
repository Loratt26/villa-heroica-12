from datetime import datetime, date as date_type, timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from .validators import validar_cedula, normalizar_cedula as _norm


class Departamento(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Departamento'
        verbose_name_plural = 'Departamentos'
        ordering = ['nombre']
        db_table = 'departamento'

    def __str__(self):
        return self.nombre


class Sede(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Sede'
        db_table = 'sede'

    def __str__(self):
        return self.nombre


class Empleado(models.Model):
    DIAS = [(i, n) for i, n in enumerate(
        ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    )]

    nombre       = models.CharField(max_length=100)
    apellido     = models.CharField(max_length=100)
    cargo        = models.CharField(max_length=150)
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT)
    usuario      = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    activo       = models.BooleanField(default=True)

    cedula = models.CharField(
        max_length=12, unique=True, null=True, blank=True,
        db_index=True, validators=[validar_cedula],
        help_text='Formato: V-12345678 o E-12345678',
    )
    foto         = models.ImageField(upload_to='fotos/', null=True, blank=True)
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida  = models.TimeField(null=True, blank=True)

    # [0,1,2,3,4] = lun–vie | [0,1,2,3,4,5] = lun–sáb | [] = sin restricción
    dias_laborables = models.JSONField(
        default=list, blank=True,
        help_text='0=Lun, 1=Mar, 2=Mié, 3=Jue, 4=Vie, 5=Sáb, 6=Dom',
    )

    sede = models.ForeignKey(
        Sede, on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados'
    )

    class Meta:
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'
        ordering = ['apellido', 'nombre']
        db_table = 'empleado'
        indexes = [
            models.Index(fields=['activo', 'apellido', 'nombre'], name='emp_activo_ap_nom_idx'),
        ]

    def __str__(self):
        return f'{self.nombre} {self.apellido}'

    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'

    def foto_url(self):
        if not self.foto:
            return None
        try:
            return self.foto.url if self.foto.storage.exists(self.foto.name) else None
        except Exception:
            return None

    def es_dia_laborable(self, fecha: date_type) -> bool:
        """True si el empleado trabaja ese día de la semana."""
        if not self.dias_laborables:
            return True  # sin restricción → siempre laborable
        return fecha.weekday() in self.dias_laborables

    def save(self, *args, **kwargs):
        if self.cedula:
            self.cedula = _norm(self.cedula)
        super().save(*args, **kwargs)

    @staticmethod
    def normalizar_cedula(raw: str) -> str:
        return _norm(raw)


class Feriado(models.Model):
    fecha       = models.DateField(unique=True)
    descripcion = models.CharField(max_length=200)

    class Meta:
        verbose_name = 'Feriado'
        ordering = ['fecha']
        db_table = 'feriado'

    def __str__(self):
        return f'{self.fecha} — {self.descripcion}'


# ── State machine ─────────────────────────────────────────────────────────────
class EstadoRegistro(models.TextChoices):
    SIN_ENTRADA        = 'SIN_ENTRADA',        'Sin entrada'
    ENTRADA_REGISTRADA = 'ENTRADA_REGISTRADA', 'Entrada registrada'
    SALIDA_REGISTRADA  = 'SALIDA_REGISTRADA',  'Salida registrada'
    CERRADO            = 'CERRADO',            'Cerrado'

    @classmethod
    def transicion_valida(cls, actual: str, siguiente: str) -> bool:
        MAPA = {
            cls.SIN_ENTRADA:        {cls.ENTRADA_REGISTRADA},
            cls.ENTRADA_REGISTRADA: {cls.SALIDA_REGISTRADA},
            cls.SALIDA_REGISTRADA:  {cls.CERRADO},
            cls.CERRADO:            set(),
        }
        return siguiente in MAPA.get(actual, set())


class RegistroAsistencia(models.Model):
    NOVEDAD = [
        ('normal',            'Normal'),
        ('tardanza',          'Tardanza'),
        ('salida_anticipada', 'Salida anticipada'),
    ]

    empleado     = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha        = models.DateField(db_index=True)
    # Turnos nocturnos: fecha_salida es el día siguiente si cruza medianoche
    fecha_salida = models.DateField(null=True, blank=True,
                                    help_text='Solo si el turno cruza medianoche.')
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida  = models.TimeField(null=True, blank=True)

    horario_entrada_esperado = models.TimeField(null=True, blank=True)
    horario_salida_esperado  = models.TimeField(null=True, blank=True)

    tipo_novedad   = models.CharField(max_length=20, choices=NOVEDAD, default='normal')
    motivo         = models.TextField(blank=True, default='')
    autorizado_por = models.ForeignKey(
        Empleado, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='autorizaciones_dadas',
    )

    estado = models.CharField(
        max_length=20,
        choices=EstadoRegistro.choices,
        default=EstadoRegistro.SIN_ENTRADA,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ip_kiosco  = models.GenericIPAddressField(null=True, blank=True)

    sede = models.ForeignKey(
        Sede, on_delete=models.SET_NULL, null=True, blank=True, related_name='registros'
    )

    class Meta:
        verbose_name = 'Registro de Asistencia'
        verbose_name_plural = 'Registros de Asistencia'
        ordering = ['-fecha', '-hora_entrada']
        unique_together = ['empleado', 'fecha']
        db_table = 'registro_asistencia'
        indexes = [
            models.Index(fields=['fecha'],                   name='reg_fecha_idx'),
            models.Index(fields=['tipo_novedad', 'fecha'],   name='reg_novedad_fecha_idx'),
            models.Index(fields=['empleado', 'fecha'],       name='reg_emp_fecha_idx'),
            models.Index(fields=['estado', 'fecha'],         name='reg_estado_fecha_idx'),
        ]

    def __str__(self):
        return f'{self.empleado} — {self.fecha}'

    def transicionar(self, nuevo_estado: str) -> bool:
        """Aplica transición si es válida. Retorna False si inválida (no guarda)."""
        if not EstadoRegistro.transicion_valida(self.estado, nuevo_estado):
            return False
        self.estado = nuevo_estado
        return True

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.horario_entrada_esperado and self.empleado.hora_entrada:
                self.horario_entrada_esperado = self.empleado.hora_entrada
            if not self.horario_salida_esperado and self.empleado.hora_salida:
                self.horario_salida_esperado = self.empleado.hora_salida
        super().save(*args, **kwargs)

    def horas_trabajadas(self) -> str:
        if not self.hora_entrada or not self.hora_salida:
            return '—'
        fecha_e = self.fecha
        fecha_s = self.fecha_salida or self.fecha
        entrada = datetime.combine(fecha_e, self.hora_entrada)
        salida  = datetime.combine(fecha_s, self.hora_salida)
        diff    = salida - entrada
        if diff.total_seconds() <= 0:
            return '—'
        mins = int(diff.total_seconds() // 60)
        return f'{mins // 60}h {mins % 60:02d}m'

    def minutos_tardanza(self) -> int:
        if not self.hora_entrada or not self.horario_entrada_esperado:
            return 0
        esperada = datetime.combine(date_type.today(), self.horario_entrada_esperado)
        real     = datetime.combine(date_type.today(), self.hora_entrada)
        return max(int((real - esperada).total_seconds() // 60), 0)

    def snapshot(self) -> dict:
        """Para AuditLog.datos_antes / datos_despues."""
        return {
            'hora_entrada': str(self.hora_entrada) if self.hora_entrada else None,
            'hora_salida':  str(self.hora_salida)  if self.hora_salida  else None,
            'tipo_novedad': self.tipo_novedad,
            'motivo':       self.motivo,
            'estado':       self.estado,
        }


# ── AuditLog ──────────────────────────────────────────────────────────────────
class AuditLog(models.Model):
    ACCIONES = [
        ('ENTRADA',          'Entrada registrada'),
        ('SALIDA',           'Salida registrada'),
        ('TARDANZA',         'Tardanza'),
        ('SALIDA_ANT',       'Salida anticipada'),
        ('EDIT_REGISTRO',    'Registro editado'),
        ('DEL_REGISTRO',     'Registro eliminado'),
        ('EMPLEADO_CREADO',  'Empleado creado'),
        ('EMPLEADO_EDITADO', 'Empleado editado'),
        ('EXPORT_CSV',       'Exportación CSV'),
        ('LOGIN',            'Login admin'),
    ]

    accion        = models.CharField(max_length=30, choices=ACCIONES, db_index=True)
    empleado      = models.ForeignKey(
        Empleado, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    realizado_por = models.ForeignKey(
        Empleado, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    timestamp     = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address    = models.GenericIPAddressField(null=True, blank=True)
    datos_antes   = models.JSONField(null=True, blank=True)
    datos_despues = models.JSONField(null=True, blank=True)
    metadata      = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-timestamp']
        indexes  = [
            models.Index(fields=['accion', 'timestamp'],   name='audit_accion_ts_idx'),
            models.Index(fields=['empleado', 'timestamp'], name='audit_emp_ts_idx'),
        ]

    def __str__(self):
        return f'{self.accion} {self.empleado} {self.timestamp:%Y-%m-%d %H:%M}'


# ── KioscoToken ───────────────────────────────────────────────────────────────
class KioscoToken(models.Model):
    """
    Token de un solo uso para el flujo kiosco.
    Garantiza que el mismo empleado no tenga dos flujos concurrentes abiertos.
    TTL: 3 minutos (configurable).
    """
    token      = models.CharField(max_length=64, unique=True, db_index=True)
    empleado   = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='+')
    accion     = models.CharField(max_length=10)   # 'entrada' | 'salida'
    creado_at  = models.DateTimeField(auto_now_add=True)
    usado      = models.BooleanField(default=False)
    expira_at  = models.DateTimeField()

    class Meta:
        db_table = 'kiosco_token'
        indexes  = [
            models.Index(fields=['token', 'usado', 'expira_at'], name='kt_token_usado_exp_idx'),
        ]

    def es_valido(self) -> bool:
        return not self.usado and timezone.now() < self.expira_at
