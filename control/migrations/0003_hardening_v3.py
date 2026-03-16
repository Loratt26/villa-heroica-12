from django.db import migrations, models
from django.utils import timezone
import control.validators
import django.db.models.deletion


def backfill_registro_timestamps(apps, schema_editor):
    RegistroAsistencia = apps.get_model('control', 'RegistroAsistencia')
    now = timezone.now()
    RegistroAsistencia.objects.filter(created_at__isnull=True).update(created_at=now)
    RegistroAsistencia.objects.filter(updated_at__isnull=True).update(updated_at=now)


class Migration(migrations.Migration):

    dependencies = [
        ('control', '0002_mejoras_v2'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='departamento',
            table='departamento',
        ),
        migrations.AlterModelTable(
            name='empleado',
            table='empleado',
        ),
        migrations.AlterModelTable(
            name='registroasistencia',
            table='registro_asistencia',
        ),
        migrations.AlterField(
            model_name='empleado',
            name='cedula',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Formato: V-12345678 o E-12345678',
                max_length=12,
                null=True,
                unique=True,
                validators=[control.validators.validar_cedula],
            ),
        ),
        migrations.AddField(
            model_name='empleado',
            name='dias_laborables',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='0=Lun, 1=Mar, 2=Mie, 3=Jue, 4=Vie, 5=Sab, 6=Dom',
            ),
        ),
        migrations.AddIndex(
            model_name='empleado',
            index=models.Index(fields=['activo', 'apellido', 'nombre'], name='emp_activo_ap_nom_idx'),
        ),
        migrations.AlterField(
            model_name='registroasistencia',
            name='fecha',
            field=models.DateField(db_index=True),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='estado',
            field=models.CharField(
                choices=[
                    ('SIN_ENTRADA', 'Sin entrada'),
                    ('ENTRADA_REGISTRADA', 'Entrada registrada'),
                    ('SALIDA_REGISTRADA', 'Salida registrada'),
                    ('CERRADO', 'Cerrado'),
                ],
                db_index=True,
                default='SIN_ENTRADA',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='fecha_salida',
            field=models.DateField(
                blank=True,
                help_text='Solo si el turno cruza medianoche.',
                null=True,
            ),
        ),
        migrations.RunPython(backfill_registro_timestamps, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='registroasistencia',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='registroasistencia',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddIndex(
            model_name='registroasistencia',
            index=models.Index(fields=['fecha'], name='reg_fecha_idx'),
        ),
        migrations.AddIndex(
            model_name='registroasistencia',
            index=models.Index(fields=['estado', 'fecha'], name='reg_estado_fecha_idx'),
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('accion', models.CharField(
                    choices=[
                        ('ENTRADA', 'Entrada registrada'),
                        ('SALIDA', 'Salida registrada'),
                        ('TARDANZA', 'Tardanza'),
                        ('SALIDA_ANT', 'Salida anticipada'),
                        ('EDIT_REGISTRO', 'Registro editado'),
                        ('DEL_REGISTRO', 'Registro eliminado'),
                        ('EMPLEADO_CREADO', 'Empleado creado'),
                        ('EMPLEADO_EDITADO', 'Empleado editado'),
                        ('EXPORT_CSV', 'Exportacion CSV'),
                        ('LOGIN', 'Login admin'),
                    ],
                    db_index=True,
                    max_length=30,
                )),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('datos_antes', models.JSONField(blank=True, null=True)),
                ('datos_despues', models.JSONField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('empleado', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='control.empleado',
                )),
                ('realizado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='control.empleado',
                )),
            ],
            options={
                'db_table': 'audit_log',
                'ordering': ['-timestamp'],
                'indexes': [
                    models.Index(fields=['accion', 'timestamp'], name='audit_accion_ts_idx'),
                    models.Index(fields=['empleado', 'timestamp'], name='audit_emp_ts_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='KioscoToken',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('accion', models.CharField(max_length=10)),
                ('creado_at', models.DateTimeField(auto_now_add=True)),
                ('usado', models.BooleanField(default=False)),
                ('expira_at', models.DateTimeField()),
                ('empleado', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='+',
                    to='control.empleado',
                )),
            ],
            options={
                'db_table': 'kiosco_token',
                'indexes': [
                    models.Index(fields=['token', 'usado', 'expira_at'], name='kt_token_usado_exp_idx'),
                ],
            },
        ),
    ]
