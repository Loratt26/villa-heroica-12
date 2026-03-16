"""
Migración hardening v3 — no destructiva.
Todos los campos nuevos son nullable o tienen default.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('control', '0002_mejoras_v2'),
    ]

    operations = [
        # ── Empleado: días laborables ──────────────────────────────────────────
        migrations.AddField(
            model_name='empleado',
            name='dias_laborables',
            field=models.JSONField(
                default=list,
                help_text='Lista de días: 0=Lun … 6=Dom. Ej: [0,1,2,3,4]',
                blank=True,
            ),
        ),

        # ── RegistroAsistencia: state machine + turnos nocturnos ───────────────
        migrations.AddField(
            model_name='registroasistencia',
            name='estado',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('SIN_ENTRADA',        'Sin entrada'),
                    ('ENTRADA_REGISTRADA', 'Entrada registrada'),
                    ('SALIDA_REGISTRADA',  'Salida registrada'),
                    ('CERRADO',            'Cerrado'),
                ],
                default='SIN_ENTRADA',
                db_index=True,
            ),
        ),
        # Turnos nocturnos: fecha_salida puede ser distinta de fecha_entrada
        migrations.AddField(
            model_name='registroasistencia',
            name='fecha_salida',
            field=models.DateField(
                null=True, blank=True,
                help_text='Solo para turnos que cruzan medianoche.',
            ),
        ),

        # ── AuditLog (nueva tabla) ─────────────────────────────────────────────
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('accion', models.CharField(
                    max_length=30,
                    choices=[
                        ('ENTRADA',         'Entrada registrada'),
                        ('SALIDA',          'Salida registrada'),
                        ('TARDANZA',        'Tardanza'),
                        ('SALIDA_ANT',      'Salida anticipada'),
                        ('EDIT_REGISTRO',   'Registro editado'),
                        ('DEL_REGISTRO',    'Registro eliminado'),
                        ('EMPLEADO_CREADO', 'Empleado creado'),
                        ('EMPLEADO_EDITADO','Empleado editado'),
                        ('EXPORT_CSV',      'Exportación CSV'),
                        ('LOGIN',           'Login admin'),
                    ],
                    db_index=True,
                )),
                ('empleado', models.ForeignKey(
                    'control.Empleado', on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True, related_name='+',
                )),
                ('realizado_por', models.ForeignKey(
                    'control.Empleado', on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True, related_name='+',
                )),
                ('timestamp',   models.DateTimeField(auto_now_add=True, db_index=True)),
                ('ip_address',  models.GenericIPAddressField(null=True, blank=True)),
                ('datos_antes', models.JSONField(null=True, blank=True)),
                ('datos_despues', models.JSONField(null=True, blank=True)),
                ('metadata',    models.JSONField(default=dict, blank=True)),
            ],
            options={
                'db_table': 'audit_log',
                'ordering': ['-timestamp'],
                'indexes': [
                    models.Index(fields=['accion', 'timestamp'],   name='audit_accion_ts_idx'),
                    models.Index(fields=['empleado', 'timestamp'], name='audit_emp_ts_idx'),
                ],
            },
        ),

        # ── KioscoToken (flujo único kiosco) ───────────────────────────────────
        migrations.CreateModel(
            name='KioscoToken',
            fields=[
                ('id',         models.BigAutoField(primary_key=True, serialize=False)),
                ('token',      models.CharField(max_length=64, unique=True, db_index=True)),
                ('empleado',   models.ForeignKey(
                    'control.Empleado', on_delete=django.db.models.deletion.CASCADE,
                    related_name='+',
                )),
                ('accion',     models.CharField(max_length=10)),   # 'entrada'|'salida'
                ('creado_at',  models.DateTimeField(auto_now_add=True)),
                ('usado',      models.BooleanField(default=False)),
                ('expira_at',  models.DateTimeField()),
            ],
            options={
                'db_table': 'kiosco_token',
                'indexes': [models.Index(fields=['token', 'usado', 'expira_at'], name='kt_token_usado_exp_idx')],
            },
        ),
    ]
