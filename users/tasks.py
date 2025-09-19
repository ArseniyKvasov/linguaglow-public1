from celery import shared_task
import requests
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
from django.core.mail import EmailMessage
from .models import EmailTemplate, CustomUser, UserOffer, EmailType, UserTariff, TariffType, SUBSCRIPTION_OFFERS, \
    TOKENS_OFFERS, UserTokenBalance
from .tokens import generate_unsubscribe_token
from django.utils import timezone
from datetime import timedelta
from api_endpoints import SMTPBZ_API_KEY

@shared_task(bind=True)
def send_bulk_emails(self, template_id, roles):
    try:
        template = EmailTemplate.objects.get(id=template_id)
    except EmailTemplate.DoesNotExist:
        return {'count': 0, 'roles': roles, 'error': 'Template not found'}

    users = CustomUser.objects.filter(
        role__in=roles,
        allow_emails=True
    ).exclude(email='').only('id', 'email', 'username')

    emails_sent = 0
    failed = []

    for user in users:
        try:
            token = generate_unsubscribe_token(user)
            unsubscribe_link = f"https://linguaglow.ru/users/unsubscribe/?uid={user.id}&token={token}"

            html = template.html_content.replace('{{ username }}', user.username)
            html += f"""
                <hr>
                <p style="font-size: 12px; color: #666;">
                    Не хотите получать такие письма? 
                    <a href="{unsubscribe_link}" style="color: #2563eb;">Отписаться от рассылки</a>
                </p>
            """

            response = requests.post(
                "https://api.smtp.bz/v1/smtp/send",
                headers={
                    'Authorization': SMTPBZ_API_KEY,
                },
                files={
                    'name': (None, 'LinguaGlow'),
                    'from': (None, 'noreply@linguaglow.ru'),
                    'subject': (None, template.title),
                    'to': (None, user.email),
                    'html': (None, html),
                },
                timeout=10
            )

            if response.status_code != 200:
                raise Exception(f"API error: {response.text}")

            emails_sent += 1
        except Exception as e:
            failed.append({
                'email': user.email,
                'error': str(e)
            })
            continue

    return {
        'count': emails_sent,
        'failed': failed,
        'roles': roles
    }

@shared_task(bind=True)
def send_sale_emails(self, offer_type: str, user_ids=None, suggested_time=8):
    """
    Отправка email-предложений.
    :param offer_type: Тип предложения (SUBSCRIPTION_OFFERS / TOKENS_OFFERS)
    :param user_ids: Список ID пользователей, кому отправлять
    :param suggested_time: Срок действия предложения в часах
    """
    try:
        template = (
            EmailTemplate.objects
            .filter(type=offer_type)
            .order_by('-created_at')
            .first()
        )
        if not template:
            return {
                'count': 0,
                'error': f'Нет шаблона для типа {offer_type}'
            }
    except Exception as e:
        return {
            'count': 0,
            'error': str(e)
        }

    users = CustomUser.objects.filter(
        id__in=user_ids,
        allow_emails=True
    ).exclude(email='').only('id', 'email', 'username')

    emails_sent = 0
    failed = []

    for user in users:
        try:
            # Проверка активной подписки
            if offer_type in SUBSCRIPTION_OFFERS:
                if UserTariff.objects.filter(
                    user=user,
                    tariff_type__in=[
                        TariffType.BASIC,
                        TariffType.PREMIUM,
                        TariffType.MAXIMUM
                    ],
                    end_date__gt=timezone.now()
                ).exists():
                    continue

            # Проверка баланса токенов
            elif offer_type in TOKENS_OFFERS:
                try:
                    if getattr(user, 'token_balance', 0) >= 100:
                        continue
                except Exception as e:
                    failed.append({
                        'email': user.email,
                        'error': f'Token balance error: {str(e)}'
                    })
                    continue

            # Генерация токена отписки
            token = generate_unsubscribe_token(user)
            unsubscribe_link = f"https://linguaglow.ru/users/unsubscribe/?uid={user.id}&token={token}"

            # Формирование HTML
            html = template.html_content.replace('{{ username }}', user.username)
            html += f"""
                <hr>
                <p style="font-size: 12px; color: #666;">
                    Не хотите получать такие письма?
                    <a href="{unsubscribe_link}" style="color: #2563eb;">Отписаться от рассылки</a>
                </p>
            """

            # Отправка через SMTP.BZ
            response = requests.post(
                "https://api.smtp.bz/v1/smtp/send",
                headers={
                    'Authorization': SMTPBZ_API_KEY,
                },
                files={
                    'name': (None, 'LinguaGlow'),
                    'from': (None, 'noreply@linguaglow.ru'),
                    'subject': (None, template.title),
                    'to': (None, user.email),
                    'html': (None, html),
                },
                timeout=10
            )

            if response.status_code != 200:
                raise Exception(f"API error: {response.text}")

            # Создание предложения с предложением в часах
            UserOffer.objects.create(
                user=user,
                offer_type=offer_type,
                start=timezone.now(),
                end=timezone.now() + timedelta(hours=suggested_time)
            )

            emails_sent += 1
        except Exception as e:
            failed.append({
                'email': user.email,
                'error': str(e)
            })
            continue

    return {
        'count': emails_sent,
        'failed': failed,
        'offer_type': offer_type
    }