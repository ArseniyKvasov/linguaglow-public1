import json
import logging
import random
import string
from datetime import timedelta, timezone

from dateutil.relativedelta import relativedelta
from django.template import Template, Context
from django.utils.html import strip_tags
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from django.contrib import messages
import requests
from django.db import transaction
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from celery.result import AsyncResult
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives

from .tasks import send_bulk_emails
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import login, get_user_model
from django.views.decorators.http import require_POST
from .forms import RegistrationForm, LoginForm, NotificationForm, EmailForm, CodeVerifyForm, ApplicationForm
from django.contrib.auth import logout
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.decorators import login_required
from .models import UserTariff, UserTokenBalance, TariffType, Role, Notification, UserNotification, CustomUser, \
    TariffStatus, EmailConfirmation, EmailTemplate, Channel, PasswordResetCode, PromoCode, \
    EmailType, UserMetrics, Application, ArseniyApplication
from django.shortcuts import render
from hub.ai_calls import get_usage, AI_MODELS
from hub.models import SiteErrorLog, UserContextLength
from .tokens import generate_unsubscribe_token
from api_endpoints import YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, SMTPBZ_API_KEY

from hub.views import activate_user_tariff


@login_required
def dashboard(request):
    return render(request, "dashboard.html")

def documents(request):
    return render(request, "users/documents.html")

def handle_redirect(request, default='home'):
    """
    Обрабатывает параметр `next` и выполняет перенаправление.
    Защищено от открытых редиректов.
    """
    next_url = request.POST.get('next', request.GET.get('next', ''))
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(default)


def login_view(request):
    next_url = request.GET.get('next', '')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        next_url = request.POST.get('next', next_url)  # получаем next из формы, если есть
        if form.is_valid():
            user = form.get_user()
            print("USER: ", user)
            if user is not None:
                login(request, user)
                print("IS_AUTH: ", str(user.is_authenticated))
                return handle_redirect(request, default='home')
    else:
        form = LoginForm()

    return render(request, 'users/login.html', {
        'form': form,
        'next': next_url
    })

def generate_verification_code(length=6):
    """Генерация случайного кода подтверждения"""
    return ''.join(random.choices(string.digits, k=length))

logger = logging.getLogger(__name__)

def register_view(request):
    next_url = request.GET.get('next', '')
    if request.GET.get('double_tokens') == '1':
        request.session['double_tokens'] = True

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        next_url = request.POST.get('next', next_url)
        double_tokens = request.session.get('double_tokens', False)  # <-- достаём из сессии

        if form.is_valid():
            request.session['registration_data'] = {
                'username': form.cleaned_data['username'],
                'email': form.cleaned_data['email'],
                'password': form.cleaned_data['password'],
                'role': form.cleaned_data.get('role', Role.STUDENT),
                'marketing_agree': True,
                'gender': form.cleaned_data.get('gender') if 'gender' in form.cleaned_data else request.POST.get(
                    'gender', CustomUser.Gender.FEMALE),
                'ref_source_id': request.session.get('ref_source'),
                'double_tokens': double_tokens,
            }

            verification_code = generate_verification_code()
            request.session['verification_code'] = verification_code
            request.session['email_for_verification'] = form.cleaned_data['email']
            request.session['code_sent'] = False

            # Редирект с next
            if next_url:
                return redirect(f'{reverse("verify_email")}?next={next_url}')
            return redirect('verify_email')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = RegistrationForm()

    return render(request, 'users/register.html', {
        'form': form,
        'next': next_url
    })

@ratelimit(key='ip', rate='10/h', block=True)
def verify_email_view(request):
    list(messages.get_messages(request))

    email = request.session.get('email_for_verification')
    if not email:
        messages.error(request, 'Сессия истекла, пожалуйста, начните регистрацию заново')
        return redirect('register')

    next_url = request.GET.get('next', 'home')

    if request.method == 'POST':
        if 'resend_code' in request.POST:
            verification_code = generate_verification_code()
            request.session['verification_code'] = verification_code
            try:
                send_mail(
                    subject='Код подтверждения регистрации',
                    message=f'Ваш код подтверждения: {verification_code}',
                    from_email='noreply@linguaglow.ru',
                    recipient_list=[email],
                    fail_silently=False
                )
                messages.success(request, 'Новый код отправлен на почту')
            except Exception as e:
                logger.exception("Ошибка при отправке письма (resend_code): %s", e)
                messages.error(request, 'Ошибка при отправке письма. Попробуйте позже.')
                return redirect('verify_email')
            request.session['code_sent'] = True
            return redirect(f'{reverse("verify_email")}?next={next_url}')

        elif 'change_email' in request.POST:
            for key in ['registration_data', 'verification_code', 'email_for_verification', 'code_sent']:
                try:
                    request.session.pop(key, None)
                except Exception as e:
                    logger.exception("Ошибка при очистке сессии (change_email): %s", e)
            return redirect('register')

        else:
            user_code = request.POST.get('verification_code', '').strip()
            session_code = str(request.session.get('verification_code', '')).strip()

            if user_code == session_code:
                registration_data = request.session.get('registration_data')
                if not registration_data:
                    messages.error(request, 'Сессия истекла, пожалуйста, зарегистрируйтесь снова')
                    return redirect('register')

                try:
                    # --- Создание пользователя ---
                    ref_source = None
                    try:
                        if registration_data.get('ref_source_id'):
                            try:
                                ref_source = Channel.objects.get(id=registration_data['ref_source_id'])
                            except Channel.DoesNotExist:
                                ref_source = None
                    except Exception as e:
                        logger.exception("Ошибка при получении ref_source: %s", e)
                        ref_source = None

                    try:
                        user = CustomUser.objects.create_user(
                            username=registration_data['username'],
                            email=registration_data['email'],
                            password=registration_data['password'],
                            role=registration_data.get('role'),
                            ref_source=ref_source,
                            allow_emails=True,
                            consent=True,
                            gender=registration_data.get('gender', CustomUser.Gender.FEMALE),
                        )
                    except Exception as e:
                        logger.exception("Ошибка при создании CustomUser: %s", e)
                        raise

                    try:
                        UserTariff.objects.create(
                            user=user,
                            tariff_type=TariffType.FREE,
                            status=TariffStatus.ACTIVE
                        )
                    except Exception as e:
                        logger.exception("Ошибка при создании UserTariff: %s", e)

                    try:
                        if user.role == Role.TEACHER:
                            extra_tokens = 200
                            if registration_data.get('double_tokens'):
                                extra_tokens *= 2
                            try:
                                UserTokenBalance.objects.create(user=user, extra_tokens=extra_tokens, tariff_tokens=0)
                            except Exception as e:
                                logger.exception("Ошибка при создании UserTokenBalance: %s", e)

                    except Exception as e:
                        logger.exception("Ошибка при обработке роли TEACHER: %s", e)

                    try:
                        UserContextLength.objects.create(user=user, context_length=4000)
                    except Exception as e:
                        logger.exception("Ошибка при создании UserContextLength: %s", e)

                except Exception as e:
                    logger.exception("Ошибка при создании пользователя: %s", e)
                    messages.error(request, "Ошибка при регистрации. Попробуйте снова.")
                    return redirect('register')

                # --- Проверка промокода ---
                try:
                    promo_code = request.session.get('promo_code') or request.COOKIES.get('promo_code')
                    if promo_code:
                        try:
                            promo = PromoCode.objects.get(code=promo_code)

                            current_start = timezone.now()
                            period_end = current_start + relativedelta(months=3)

                            activate_user_tariff(
                                user=user,
                                tariff_type=TariffType.PREMIUM,
                                duration="MONTH",
                                amount_paid=0,
                                full_price=0,
                                period_start=current_start,
                                period_end=period_end
                            )

                            try:
                                user.present_type = "TOKENS"
                                user.save()
                            except Exception as e:
                                logger.exception("Ошибка при сохранении пользователя после активации промо: %s", e)

                            try:
                                promo.delete()
                            except Exception as e:
                                logger.exception("Ошибка при удалении промокода: %s", e)

                            messages.success(request, "Активирован тариф Премиум по промокоду на 3 месяца!")
                        except PromoCode.DoesNotExist:
                            pass
                        except Exception as e:
                            logger.exception("Ошибка при обработке промокода: %s", e)
                except Exception as e:
                    logger.exception("Ошибка при активации промокода: %s", e)
                    # промо не активировался, но регистрация идёт дальше

                # --- Очистка сессии ---
                for key in ['registration_data', 'verification_code', 'email_for_verification', 'code_sent']:
                    try:
                        request.session.pop(key, None)
                    except Exception as e:
                        logger.exception("Ошибка при очистке сессии (после регистрации): %s", e)

                try:
                    login(request, user)
                except Exception as e:
                    logger.exception("Ошибка при логине пользователя после регистрации: %s", e)
                    messages.error(request, "Ошибка при входе в аккаунт. Попробуйте войти вручную.")
                    return redirect('login')

                # --- Отправка приветственного письма для учителей (если есть шаблон) ---
                if user.role == Role.TEACHER:
                    try:
                        welcome_template = None
                        try:
                            welcome_template = EmailTemplate.objects.filter(type=EmailType.WELCOME).first()
                        except Exception as e:
                            logger.exception("Ошибка при получении EmailTemplate.WELCOME: %s", e)

                        if welcome_template:
                            try:
                                subject = welcome_template.title or 'Добро пожаловать в LinguaGlow'
                                html_content = welcome_template.html_content or ''

                                # Подставляем {{ username }} через Django Template
                                t = Template(html_content)
                                c = Context({'username': user.username})
                                rendered_html = t.render(c)

                                # SMTP.BZ API
                                SMTPBZ_API_URL = "https://api.smtp.bz/v1/smtp/send"

                                response = requests.post(
                                    SMTPBZ_API_URL,
                                    headers={'Authorization': SMTPBZ_API_KEY},
                                    files={
                                        'name': (None, 'LinguaGlow'),
                                        'from': (None, 'noreply@linguaglow.ru'),
                                        'subject': (None, subject),
                                        'to': (None, user.email),
                                        'html': (None, rendered_html),
                                    }
                                )

                                if response.status_code != 200:
                                    raise Exception(f"SMTP.BZ API error: {response.text}")

                                logger.info(
                                    "Отправлено приветственное письмо учителю id=%s email=%s",
                                    user.id,
                                    user.email
                                )
                            except Exception as e:
                                logger.exception("Ошибка при отправке приветственного письма через SMTP.BZ: %s", e)
                        else:
                            logger.info("Шаблон WELCOME не найден — приветственное письмо не отправлено.")

                        metrics, _ = UserMetrics.objects.get_or_create(user=user)
                        metrics.update_activity()
                    except Exception as e:
                        logger.exception("Непредвиденная ошибка при попытке отправить WELCOME письмо: %s", e)

                return redirect(next_url)

            else:
                messages.error(request, 'Неверный код подтверждения')

    return render(request, 'users/verify_email.html', {
        'email': email,
        'marketing_agree': request.session.get('registration_data', {}).get('marketing_agree', False),
        'code_sent': request.session.get('code_sent', False),
        'next': next_url
    })

@ratelimit(key='ip', rate='10/h', block=True)
def send_verification_code(request):
    # Проверяем наличие email в сессии
    if not request.session.get('email_for_verification'):
        print("Ошибка: сессия истекла, email для верификации отсутствует")
        return JsonResponse({'status': 'error', 'message': 'Сессия истекла'})

    # Проверяем, был ли код уже отправлен
    if not request.session.get('code_sent', False):
        try:
            # Получаем код и email из сессии
            verification_code = request.session['verification_code']
            email = request.session['email_for_verification']
            print(f"Отправка кода {verification_code} на email: {email}")

            # Конфигурация SMTP.BZ
            SMTPBZ_API_URL = "https://api.smtp.bz/v1/smtp/send"

            # HTML шаблон письма
            html_content = f"""
            <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                        .code {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
                    </style>
                </head>
                <body>
                    <p>Здравствуйте!</p>
                    <p>Ваш код подтверждения для LinguaGlow:</p>
                    <p class="code">{verification_code}</p>
                    <p>Если вы не запрашивали этот код, пожалуйста, проигнорируйте это письмо.</p>
                    <p>С уважением,<br>Команда LinguaGlow</p>
                </body>
            </html>
            """

            # Отправка через SMTP.BZ API
            response = requests.post(
                SMTPBZ_API_URL,
                headers={
                    'Authorization': SMTPBZ_API_KEY,
                },
                files={
                    'name': (None, 'LinguaGlow'),
                    'from': (None, 'noreply@linguaglow.ru'),
                    'subject': (None, 'Код подтверждения LinguaGlow'),
                    'to': (None, email),
                    'html': (None, html_content),
                }
            )

            # Проверка ответа
            if response.status_code != 200:
                raise Exception(f"SMTP.BZ API error: {response.text}")

            # Обновляем сессию
            request.session['code_sent'] = True
            print("Код успешно отправлен")
            return JsonResponse({
                'status': 'success',
                'response': response.json()
            })

        except Exception as e:
            print(f"Произошла ошибка при отправке кода: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })

    # Если код уже был отправлен
    print("Код уже был отправлен ранее")
    return JsonResponse({'status': 'already_sent'})

def verify_code(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('forgot_password')

    next_url = request.GET.get('next', 'home')  # получаем параметр next

    if request.method == "POST":
        form = CodeVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code'].strip()
            new_password = form.cleaned_data['new_password']

            try:
                user = CustomUser.objects.get(email=email)
                reset_obj = PasswordResetCode.objects.filter(user=user, code=code).last()

                if not reset_obj:
                    messages.error(request, "Неверный код")
                    return redirect('verify_code')

                if reset_obj.is_expired():
                    messages.error(request, "Код истёк")
                    return redirect('forgot_password')

                # Меняем пароль
                user.password = make_password(new_password)
                user.save()

                # Удаляем все коды для этого юзера
                PasswordResetCode.objects.filter(user=user).delete()

                messages.success(request, "Пароль успешно изменён")
                return redirect(next_url)  # редирект на next_url

            except CustomUser.DoesNotExist:
                messages.error(request, "Пользователь не найден")
                return redirect('forgot_password')
    else:
        form = CodeVerifyForm()

    return render(request, 'users/verify_code.html', {'form': form, 'next': next_url})


@ratelimit(key='ip', rate='10/h', block=True)
def forgot_password(request):
    next_url = request.GET.get('next', '')
    if request.method == "POST":
        form = EmailForm(request.POST)
        next_url = request.POST.get('next', next_url)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                messages.error(request, "Пользователь с таким email не найден")
                return render(request, 'users/forgot_password.html',
                           {'form': form, 'next': next_url})

            # Генерируем код
            code = f"{random.randint(100000, 999999)}"

            # Сохраняем в БД
            PasswordResetCode.objects.create(user=user, code=code)

            # HTML шаблон письма
            html_content = f"""
            <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                        .code {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <p>Здравствуйте!</p>
                        <p>Для восстановления пароля в LinguaGlow используйте следующий код:</p>
                        <p class="code">{code}</p>
                        <p>Код действителен в течение 1 часа.</p>
                        <p>Если вы не запрашивали сброс пароля, проигнорируйте это письмо.</p>
                        <p>С уважением,<br>Команда LinguaGlow</p>
                    </div>
                </body>
            </html>
            """

            # Отправка через SMTP.BZ API
            try:
                response = requests.post(
                    "https://api.smtp.bz/v1/smtp/send",
                    headers={
                        'Authorization': SMTPBZ_API_KEY,
                    },
                    files={
                        'name': (None, 'LinguaGlow'),
                        'from': (None, 'noreply@linguaglow.ru'),
                        'subject': (None, 'Восстановление пароля LinguaGlow'),
                        'to': (None, email),
                        'html': (None, html_content),
                    },
                    timeout=10  # Таймаут 10 секунд
                )

                if response.status_code != 200:
                    raise Exception(f"Ошибка отправки письма: {response.text}")

            except Exception as e:
                messages.error(request, f"Ошибка при отправке письма: {str(e)}")
                return render(request, 'users/forgot_password.html',
                           {'form': form, 'next': next_url})

            request.session['reset_email'] = email
            if next_url:
                request.session['next_after_reset'] = next_url

            messages.success(request, "Код восстановления отправлен на вашу почту")
            return redirect('verify_code')
    else:
        form = EmailForm()

    return render(request, 'users/forgot_password.html',
                {'form': form, 'next': next_url})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def hide_notification(request, notification_id):
    if request.method == 'POST':
        notif = get_object_or_404(Notification, pk=notification_id)
        UserNotification.objects.update_or_create(
            user=request.user,
            notification=notif,
            defaults={'is_hidden': True, 'hidden_at': now()}
        )
    return redirect(request.META.get('HTTP_REFERER', '/'))



@staff_member_required
def website_stats(request):
    notification_form = NotificationForm(request.POST or None)
    success_message = ''
    error_message = ''

    if request.method == 'POST' and 'title' in request.POST:
        if notification_form.is_valid():
            instance = notification_form.save()
            roles = ', '.join(notification_form.cleaned_data.get('target_roles', []))
            success_message = roles
        else:
            error_message = 'Форма содержит ошибки'

    context = {
        'notification_form': notification_form,
        'notifications': Notification.objects.order_by('-created_at'),
        'success_message': success_message,
        'error_message': error_message,
    }
    return render(request, 'admin/stats.html', context)

@staff_member_required
def delete_notification(request, pk):
    if request.method == 'POST':
        notification = get_object_or_404(Notification, pk=pk)
        notification.delete()
    return redirect('website_stats')  # имя URL-шаблона, где отображается форма

@staff_member_required
def delete_site_error(request, pk):
    error = get_object_or_404(SiteErrorLog, pk=pk)
    error.delete()
    return redirect(request.META.get('HTTP_REFERER', '/'))

@staff_member_required
def create_or_update_email_template(request):
    template_id = request.POST.get('template_id')
    title = request.POST.get('title')
    html_content = request.POST.get('html_content')
    type_ = request.POST.get('type', 'generic')

    if template_id:
        template = get_object_or_404(EmailTemplate, id=template_id)
        template.title = title
        template.html_content = html_content
        template.type = type_
        template.save()
    else:
        EmailTemplate.objects.create(
            title=title,
            html_content=html_content,
            type=type_,
        )

    return redirect(request.META.get('HTTP_REFERER', '/'))

@staff_member_required
def delete_email_template(request):
    template_id = request.POST.get('template_id')
    EmailTemplate.objects.filter(id=template_id).delete()
    return JsonResponse({'success': True})

@require_POST
@staff_member_required
def send_email_template(request):
    try:
        data = json.loads(request.body)
        template_id = data.get('template_id')
        is_test = data.get('test', False)
        roles = data.get('roles', [])

        template = get_object_or_404(EmailTemplate, id=template_id)

        if is_test:
            email = EmailMessage(
                subject=template.title,
                body=template.html_content.replace('{{ username }}', 'Арсений'),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=['arsenijtam@gmail.com'],
            )
            email.content_subtype = "html"
            email.send()
            return JsonResponse({'success': True, 'count': 1, 'roles': []})

        # запуск фоновой задачи
        task = send_bulk_emails.delay(template_id, roles)
        return JsonResponse({'success': True, 'count': 'pending', 'roles': roles, 'task_id': task.id})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@staff_member_required
def check_email_task_status(request, task_id):
    result = AsyncResult(task_id)

    response = {
        'task_id': task_id,
        'status': result.status,
    }

    if result.status == 'SUCCESS':
        response['result'] = result.result
    elif result.status == 'FAILURE':
        response['error'] = str(result.result)

    return JsonResponse(response)

@staff_member_required
@require_POST
def create_channel(request):
    name = request.POST.get('name')
    code = request.POST.get('code')
    if name and code:
        Channel.objects.create(name=name, code=code)
    return redirect(request.META.get('HTTP_REFERER', '/'))

@staff_member_required
@require_POST
def delete_channel(request, pk):
    channel = get_object_or_404(Channel, pk=pk)
    channel.delete()
    return redirect(request.META.get('HTTP_REFERER', '/'))

@staff_member_required
def create_promo(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        if code:
            PromoCode.objects.get_or_create(code=code)
            messages.success(request, f"Промокод {code} создан")
    return redirect('website_stats')

@staff_member_required
def delete_promo(request, promo_id):
    promo = get_object_or_404(PromoCode, id=promo_id)
    promo.delete()
    messages.success(request, f"Промокод {promo.code} удалён")
    return redirect('website_stats')



@ratelimit(key='ip', rate='10/d', block=True)
def unsubscribe_page(request):
    uid = request.GET.get("uid")
    token = request.GET.get("token")
    return render(request, "emails/unsubscribe_page.html", {"uid": uid, "token": token})

@require_POST
def unsubscribe_confirm(request):
    uid = request.POST.get("uid")
    token = request.POST.get("token")
    User = get_user_model()

    try:
        user = User.objects.get(id=uid)
        expected_token = generate_unsubscribe_token(user)
        if not constant_time_compare(token, expected_token):
            return JsonResponse({"error": "Invalid token"}, status=403)

        user.allow_emails = False
        user.save()
        return JsonResponse({"status": "ok"})

    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)






SMTPBZ_API_URL = "https://api.smtp.bz/v1/smtp/send"

@require_POST
@staff_member_required
def send_email_template(request):
    try:
        data = json.loads(request.body)
        template_id = data.get('template_id')
        is_test = data.get('test', False)
        roles = data.get('roles', [])
        test_recipient = data.get('test_email')  # опционально можно передать адрес для теста

        template = get_object_or_404(EmailTemplate, id=template_id)

        # ТЕСТОВАЯ МОНО-ОТПРАВКА через SMTP.BZ API
        if is_test:
            recipient_email = test_recipient or 'arsenijtam@gmail.com'
            # можно заменить переменные шаблона здесь, прим.: {{ username }}
            html_content = template.html_content.replace('{{ username }}', 'Арсений')

            try:
                response = requests.post(
                    SMTPBZ_API_URL,
                    headers={'Authorization': SMTPBZ_API_KEY},
                    files={
                        'name': (None, 'LinguaGlow'),
                        'from': (None, 'noreply@linguaglow.ru'),
                        'subject': (None, template.title),
                        'to': (None, recipient_email),
                        'html': (None, html_content),
                    },
                    timeout=15
                )
            except Exception as exc:
                logger.exception("Ошибка при отправке тестового письма через SMTP API: %s", exc)
                return JsonResponse({'success': False, 'error': str(exc)}, status=500)

            if response.ok:
                logger.info("Тестовое письмо отправлено на %s (template_id=%s)", recipient_email, template_id)
                return JsonResponse({'success': True, 'count': 1, 'roles': []})
            else:
                logger.warning("SMTP API вернул ошибку при тестовой отправке: %s — %s", response.status_code, response.text)
                return JsonResponse({'success': False, 'error': response.text, 'status_code': response.status_code}, status=500)

        # МАССОВАЯ ОТПРАВКА (асинхронно через Celery task)
        # task должен реализовывать отправку через API (пример ниже)
        task = send_bulk_emails.delay(template_id, roles)
        return JsonResponse({'success': True, 'count': 'pending', 'roles': roles, 'task_id': task.id})

    except Exception as e:
        logger.exception("Ошибка в send_email_template: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def send_gift_congrat_email(user, present_type):
    recipient_email = user.email
    present_label = "🎁 7 дней Premium" if present_type == "Подписка" else "✨ 500 токенов"

    html_content = f"""
    <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width,initial-scale=1" />
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    color: #111827;
                    background: #f8fafc;
                    margin: 0;
                    padding: 0;
                }}
                .wrapper {{ width: 100%; padding: 20px 12px; }}
                .card {{
                    max-width: 640px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 12px;
                    padding: 20px;
                    box-shadow: 0 6px 22px rgba(16, 24, 40, 0.06);
                    text-align: center;
                }}
                h1 {{ font-size: 22px; margin: 0 0 12px; color: #0f172a; }}
                p.lead {{ margin: 0 0 16px; color: #374151; font-size: 16px; }}
                a.button {{
                    display: inline-block;
                    margin-top: 14px;
                    padding: 12px 22px;
                    background: #10b981;
                    color: #fff !important;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: bold;
                    text-decoration: none;
                }}
                .footer {{ margin-top: 18px; font-size: 13px; color: #6b7280; }}
            </style>
        </head>
        <body>
            <div class="wrapper">
                <div class="card">
                    <h1>Поздравляем! 🎉</h1>
                    <p class="lead">Ты выполнил финальный шаг и получил свой подарок:</p>
                    <a href="https://linguaglow.ru/" class="button">{present_label}</a>
                    <div class="footer">Спасибо, что с нами!<br/>Команда LinguaGlow</div>
                </div>
            </div>
        </body>
    </html>
    """

    try:
        response = requests.post(
            SMTPBZ_API_URL,
            headers={'Authorization': SMTPBZ_API_KEY},
            files={
                'name': (None, 'LinguaGlow'),
                'from': (None, 'noreply@linguaglow.ru'),
                'subject': (None, '🎉 Ваш подарок в LinguaGlow'),
                'to': (None, recipient_email),
                'html': (None, html_content),
            },
            timeout=15
        )
    except Exception as exc:
        logger.exception("Ошибка при отправке письма с подарком: %s", exc)
    else:
        if response.ok:
            logger.info("Письмо с подарком отправлено на %s", recipient_email)
        else:
            logger.warning(
                "SMTP.BZ ошибка при отправке письма с подарком: %s — %s",
                response.status_code, response.text
            )

HOME_URL = "https://linguaglow.ru/"


def studynote(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("thanks")  # страница спасибо
    else:
        form = ApplicationForm()

    return render(request, "additional/studynote.html", {"form": form})

def delete_application(request, pk):
    application = get_object_or_404(Application, pk=pk)
    application.delete()
    return redirect(reverse("applications_list"))


def tutor_profile(request):
    if request.method == "POST":
        parent_name = request.POST.get('parent')
        phone = request.POST.get('phone')
        child_name = request.POST.get('child')
        grade = request.POST.get('grade')
        goals = request.POST.get('goals')
        consent = request.POST.get('agree')

        # Здесь можно добавить сохранение в базу данных или отправку письма
        # Например, через Django Email или запись в модель TutorRequest
        # TutorRequest.objects.create(parent=parent_name, phone=phone, child=child_name, grade=grade, goals=goals, consent=consent)

        return render(request, 'additional/arseniy_profile.html', {
        'success': True
        })

    return render(request, 'additional/arseniy_profile.html')

def fastlesson(request):
    return render(request, 'additional/fastlesson.html')

SMTPBZ_API_URL = "https://api.smtp.bz/v1/smtp/send"

@csrf_exempt
def handle_application(request):
    if request.method == "POST":
        child_name = request.POST.get("child_name")
        grade = request.POST.get("grade")
        phone = request.POST.get("phone")

        if not (child_name and grade and phone):
            return JsonResponse({"error": "Заполните все поля"}, status=400)

        app = ArseniyApplication.objects.create(
            child_name=child_name,
            grade=grade,
            phone=phone
        )

        html_content = f"""
        <h2>Новая заявка</h2>
        <p><b>Имя ребёнка:</b> {child_name}</p>
        <p><b>Класс:</b> {grade}</p>
        <p><b>Телефон:</b> {phone}</p>
        <p><i>Дата:</i> {app.created_at.strftime('%d.%m.%Y %H:%M')}</p>
        """

        import traceback

        try:
            response = requests.post(
                SMTPBZ_API_URL,
                headers={
                    'Authorization': "nyA6qihpEJpIIJcR3cN1GZgc4AbMuNVIbmDs",
                },
                files={
                    'name': (None, 'LinguaGlow'),
                    'from': (None, 'noreply@linguaglow.ru'),
                    'subject': (None, 'Новая заявка на LinguaGlow'),
                    'to': (None, 'arsenijtam@gmail.com'),
                    'html': (None, html_content),
                }
            )
        except Exception as e:
            print("Exception while sending email:", e)
            traceback.print_exc()
            return JsonResponse({"error": f"Ошибка отправки письма: {e}"}, status=500)

        if response.status_code != 200:
            return JsonResponse({"error": f"Ошибка отправки письма: {response.text}"}, status=500)

        return JsonResponse({"message": "Заявка успешно отправлена!"})

    return JsonResponse({"error": "Метод не поддерживается"}, status=405)

def delete_application(request, pk):
    if request.method == "POST":
        app = get_object_or_404(ArseniyApplication, pk=pk)
        app.delete()
        return redirect("/users/stats/")  # сюда вернёмся после удаления
    return HttpResponseForbidden("Удаление только POST-запросом")