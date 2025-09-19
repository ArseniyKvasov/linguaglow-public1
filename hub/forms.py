from django import forms
from .models import Classroom

class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите название класса'
            })
        }

class SiteErrorForm(forms.Form):
    title = forms.CharField(
        label='Где произошла ошибка?',
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
        })
    )
    content = forms.CharField(
        label='Описание ошибки, какое устройство Вы использовали (телефон, компьютер) и какой браузер (Google Chrome, Yandex, Firefox)?',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 6,
        })
    )



