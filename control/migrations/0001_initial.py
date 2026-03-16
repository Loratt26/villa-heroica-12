from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Departamento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, verbose_name='Nombre')),
            ],
            options={
                'verbose_name': 'Departamento',
                'verbose_name_plural': 'Departamentos',
                'ordering': ['nombre'],
            },
        ),
        migrations.CreateModel(
            name='Empleado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, verbose_name='Nombre')),
                ('apellido', models.CharField(max_length=100, verbose_name='Apellido')),
                ('cargo', models.CharField(max_length=150, verbose_name='Cargo')),
                ('activo', models.BooleanField(default=True, verbose_name='Activo')),
                ('departamento', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='control.departamento',
                    verbose_name='Departamento',
                )),
                ('usuario', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='auth.user',
                    verbose_name='Usuario del sistema',
                )),
            ],
            options={
                'verbose_name': 'Empleado',
                'verbose_name_plural': 'Empleados',
                'ordering': ['apellido', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='RegistroAsistencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(verbose_name='Fecha')),
                ('hora_entrada', models.TimeField(blank=True, null=True, verbose_name='Hora de Entrada')),
                ('hora_salida', models.TimeField(blank=True, null=True, verbose_name='Hora de Salida')),
                ('empleado', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='control.empleado',
                    verbose_name='Empleado',
                )),
            ],
            options={
                'verbose_name': 'Registro de Asistencia',
                'verbose_name_plural': 'Registros de Asistencia',
                'ordering': ['-fecha', '-hora_entrada'],
                'unique_together': {('empleado', 'fecha')},
            },
        ),
    ]
