"""
Migración incremental — no destructiva.
Agrega campos nuevos a tablas existentes. Todo nullable para compatibilidad.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('control', '0001_initial'),
    ]

    operations = [
        # ── Sede (nueva tabla) ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='Sede',
            fields=[
                ('id',     models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('codigo', models.CharField(max_length=20, unique=True)),
                ('nombre', models.CharField(max_length=100)),
                ('activa', models.BooleanField(default=True)),
            ],
            options={'db_table': 'sede', 'verbose_name': 'Sede'},
        ),

        # ── Feriado (nueva tabla) ──────────────────────────────────────────────
        migrations.CreateModel(
            name='Feriado',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('fecha',       models.DateField(unique=True)),
                ('descripcion', models.CharField(max_length=200)),
            ],
            options={'db_table': 'feriado', 'verbose_name': 'Feriado', 'ordering': ['fecha']},
        ),

        # ── Empleado: nuevos campos ────────────────────────────────────────────
        migrations.AddField(
            model_name='empleado',
            name='cedula',
            field=models.CharField(max_length=12, null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name='empleado',
            name='foto',
            field=models.ImageField(upload_to='fotos/', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='empleado',
            name='hora_entrada',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='empleado',
            name='hora_salida',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='empleado',
            name='sede',
            field=models.ForeignKey(
                to='control.Sede', on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True, related_name='empleados',
            ),
        ),
        migrations.AlterField(
            model_name='empleado',
            name='nombre',
            field=models.CharField(max_length=100),
        ),

        # ── RegistroAsistencia: nuevos campos ──────────────────────────────────
        migrations.AddField(
            model_name='registroasistencia',
            name='horario_entrada_esperado',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='horario_salida_esperado',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='tipo_novedad',
            field=models.CharField(
                max_length=20,
                choices=[('normal','Normal'),('tardanza','Tardanza'),('salida_anticipada','Salida anticipada')],
                default='normal',
            ),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='motivo',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='autorizado_por',
            field=models.ForeignKey(
                to='control.Empleado', on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True, related_name='autorizaciones_dadas',
            ),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='ip_kiosco',
            field=models.GenericIPAddressField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='registroasistencia',
            name='sede',
            field=models.ForeignKey(
                to='control.Sede', on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True, related_name='registros',
            ),
        ),

        # ── Índices para reportes ──────────────────────────────────────────────
        migrations.AddIndex(
            model_name='registroasistencia',
            index=models.Index(fields=['tipo_novedad', 'fecha'], name='reg_novedad_fecha_idx'),
        ),
        migrations.AddIndex(
            model_name='registroasistencia',
            index=models.Index(fields=['empleado', 'fecha'], name='reg_emp_fecha_idx'),
        ),
    ]
