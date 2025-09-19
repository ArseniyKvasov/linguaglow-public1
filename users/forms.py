from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm
from django.contrib.auth import authenticate, login
from django.db.models import Q
from .models import CustomUser, Notification, Role


# forms.py
class RegistrationForm(forms.ModelForm):
    email = forms.EmailField(
        label='Электронная почта',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Электронная почта'
        })
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'id': 'password-input',
            'class': 'form-control',
            'placeholder': 'Придумайте пароль'
        })
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'username', 'role']  # Добавили email
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ваше имя пользователя'
            }),
            'role': forms.Select(attrs={
                'class': 'form-control form-select',
                'placeholder': 'Выберите роль'
            }),
        }
        labels = {
            'email': 'Email',
            'username': 'Имя пользователя',
            'role': 'Роль'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Делаем роль по умолчанию TEACHER
        from users.models import Role  # если у тебя enum
        self.fields['role'].initial = Role.TEACHER

    def clean_email(self):
        email = self.cleaned_data['email']
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        if CustomUser.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким именем уже существует.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.email = self.cleaned_data['email']  # Сохраняем email
        if commit:
            user.save()
        return user



class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Имя пользователя или Email',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Имя пользователя или Email'
        })
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Пароль'
        })
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            # Ищем пользователя по username или email
            user_obj = CustomUser.objects.filter(
                Q(username=username) | Q(email=username)
            ).first()

            if user_obj is None:
                raise forms.ValidationError("Неверное имя пользователя или email.")

            if not user_obj.check_password(password):
                raise forms.ValidationError("Неверный пароль.")

            # Проверка активности
            self.confirm_login_allowed(user_obj)

            # Аутентификация (важно!)
            authenticated_user = authenticate(
                self.request,
                username=user_obj.username,
                password=password
            )
            if authenticated_user is None:
                raise forms.ValidationError("Не удалось выполнить вход.")

            self.user_cache = authenticated_user  # теперь get_user() вернёт реального юзера
            self.cleaned_data['username'] = user_obj.username

        return self.cleaned_data


class CustomPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super(CustomPasswordResetForm, self).__init__(*args, **kwargs)
        # Добавляем классы CSS к полю email
        self.fields['email'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Введите email для сброса пароля'
        })

class NotificationForm(forms.ModelForm):
    target_roles = forms.MultipleChoiceField(
        choices=Role.choices,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label='Роли получателей'
    )

    class Meta:
        model = Notification
        fields = ['title', 'message', 'link', 'is_active', 'target_roles']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Заголовок',
                'aria-label': 'Заголовок уведомления'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Текст уведомления',
                'aria-label': 'Текст уведомления'
            }),
            'link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ссылка для кнопки «Подробнее»',
                'aria-label': 'Ссылка уведомления (необязательно)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'aria-label': 'Активно'
            }),
        }
        labels = {
            'title': 'Заголовок',
            'message': 'Текст уведомления',
            'link': 'Ссылка (кнопка «Подробнее»)',
            'is_active': 'Активно',
            'target_roles': 'Роли получателей'
        }


class EmailForm(forms.Form):
    email = forms.EmailField(label="Ваша почта")

    def clean_email(self):
        email = self.cleaned_data['email']
        if not CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email не найден")
        return email


class CodeVerifyForm(forms.Form):
    code = forms.CharField(max_length=6, label="Код из письма")
    new_password = forms.CharField(
        widget=forms.PasswordInput,
        label="Новый пароль",
        min_length=6
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        label="Повторите пароль"
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('new_password') != cleaned_data.get('confirm_password'):
            raise forms.ValidationError("Пароли не совпадают")
        return cleaned_data






from .models import Application


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = [
            "name",
            "contact",
            "role",
            "subject",
            "tg_homework",
            "ai_checking",
            "workflow",
            "tester",
        ]
        labels = {
            "name": "Имя (необязательно)",
            "contact": "Контакт (Telegram или email)",
            "role": "Ваша роль",
            "subject": "Какой предмет вы преподаёте?",
            "tg_homework": "Готовы ли вы отправлять домашние задания ученикам в Telegram?",
            "ai_checking": "Хотели бы вы, чтобы ИИ проверял часть ответов?",
            "workflow": "Как сейчас проверяете ДЗ?",
            "tester": "Хочу участвовать в тестировании",
        }
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Иван Иванов"
            }),
            "contact": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "@username или you@example.com"
            }),
            "role": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Например: математика"
            }),
            "tg_homework": forms.Select(attrs={"class": "form-select"}),
            "ai_checking": forms.Select(attrs={"class": "form-select"}),
            "workflow": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Например: Word + фото домашних заданий"
            }),
            "tester": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }