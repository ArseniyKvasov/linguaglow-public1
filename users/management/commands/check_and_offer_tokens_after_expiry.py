# users/management/commands/check_and_offer_tokens_after_expiry.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import UserTariff, UserOffer, EmailType, TariffType
from users.tasks import send_sale_emails

class Command(BaseCommand):
    help = (
        "Проверяет пользователей с тарифами BASIC, PREMIUM, MAXIMUM, "
        "у которых подписка истекла 96-120 часов назад (4-5 дней). "
        "Если в последние 6 месяцев не предлагали 2000 токенов — отправляет такое предложение, "
        "иначе — 1000 токенов. Каждое предложение действует сутки."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            start_period = now - timedelta(hours=120)  # 120 часов назад
            end_period = now - timedelta(hours=96)     # 96 часов назад

            expired_tariffs = UserTariff.objects.filter(
                tariff_type__in=[TariffType.BASIC, TariffType.PREMIUM, TariffType.MAXIMUM],
                end_date__range=(start_period, end_period)
            )

            offer_map = {}

            for tariff in expired_tariffs:
                try:
                    user = tariff.user

                    six_months_ago = now - timedelta(days=180)
                    offered_2000_tokens = UserOffer.objects.filter(
                        user=user,
                        offer_type=EmailType.GIFT_2000_TOKENS,
                        start__gte=six_months_ago
                    ).exists()

                    if not offered_2000_tokens:
                        offer_type = EmailType.GIFT_2000_TOKENS
                    else:
                        offer_type = EmailType.GIFT_1000_TOKENS

                    already_sent = UserOffer.objects.filter(
                        user=user,
                        offer_type=offer_type,
                        start__gte=now - timedelta(days=1)
                    ).exists()

                    if already_sent:
                        continue

                    offer_map.setdefault(offer_type, []).append(user.id)

                except Exception as e:
                    self.stderr.write(f"[OFFER_CHECK] Ошибка при обработке тарифа {tariff.id}, пользователь {tariff.user_id}: {e}")
                    continue

            for offer_type, user_ids in offer_map.items():
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=user_ids,
                        suggested_time=8
                    )
                except Exception as e:
                    self.stderr.write(f"[EMAIL_SEND] Ошибка при отправке email для предложения {offer_type}: {e}")

            self.stdout.write(self.style.SUCCESS('check_and_offer_tokens_after_expiry выполнена успешно'))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи предложения токенов после окончания тарифа: {e}")