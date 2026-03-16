from django import forms
from django.contrib.auth.models import User
from .models import Empleado
from .validators import validar_cedula


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model  = Empleado
        fields = ['nombre', 'apellido', 'cargo', 'departamento',
                  'cedula', 'foto', 'hora_entrada', 'hora_salida', 'activo']
        widgets = {
            'nombre':       forms.TextInput(attrs={'class': 'form-control'}),
            'apellido':     forms.TextInput(attrs={'class': 'form-control'}),
            'cargo':        forms.TextInput(attrs={'class': 'form-control'}),
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'cedula':       forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'V-12345678'
            }),
            'hora_entrada': forms.TimeInput(attrs={
                'class': 'form-control', 'type': 'time'
            }),
            'hora_salida':  forms.TimeInput(attrs={
                'class': 'form-control', 'type': 'time'
            }),
            'activo':       forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_cedula(self):
        value = self.cleaned_data.get('cedula', '').strip()
        if not value:
            return value
        # Delegar al validador centralizado — lanza ValidationError si inválido
        return validar_cedula(value)

    def clean(self):
        cleaned = super().clean()
        entrada = cleaned.get('hora_entrada')
        salida  = cleaned.get('hora_salida')
        # Evitar horario incoherente
        if entrada and salida and salida <= entrada:
            self.add_error('hora_salida', 'La hora de salida debe ser posterior a la de entrada.')
        return cleaned


class ReporteForm(forms.Form):
    TIPOS = [
        ('asistencias',   'Asistencias'),
        ('inasistencias', 'Inasistencias'),
    ]
    empleado = forms.ModelChoiceField(
        queryset=Empleado.objects.filter(activo=True).order_by('apellido', 'nombre'),
        required=False,
        empty_label='— Todos los empleados —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    fecha_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Desde',
    )
    fecha_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Hasta',
    )
    tipo_reporte = forms.ChoiceField(
        choices=TIPOS,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tipo',
        initial='asistencias',
    )

    def clean(self):
        cleaned = super().clean()
        fi = cleaned.get('fecha_inicio')
        ff = cleaned.get('fecha_fin')
        if fi and ff and ff < fi:
            self.add_error('fecha_fin', 'La fecha hasta debe ser posterior a la fecha desde.')
        return cleaned


class CrearUsuarioForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=6,
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model  = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get('password1'), self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return p2

    def save(self, commit=True):
        u = super().save(commit=False)
        u.set_password(self.cleaned_data['password1'])
        if commit:
            u.save()
        return u


class EditarUsuarioForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'is_active':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CambiarPasswordForm(forms.Form):
    password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=6,
    )
    password2 = forms.CharField(
        label='Confirmar',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get('password1'), self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return p2
