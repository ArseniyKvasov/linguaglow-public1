# users/management/commands/check_and_offer_30_percent_discount.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import UserTariff, UserOffer, EmailType, TariffType
from users.tasks import send_sale_emails

class Command(BaseCommand):
    help = "Проверяет истёкшие тарифы 6-7 дней назад и предлагает скидку 30%"

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            start_period = now - timedelta(hours=168)  # 7 дней назад
            end_period = now - timedelta(hours=144)    # 6 дней назад

            expired_tariffs = UserTariff.objects.filter(
                tariff_type__in=[
                    TariffType.BASIC,
                    TariffType.PREMIUM,
                    TariffType.MAXIMUM
                ],
                end_date__range=(start_period, end_period)
            )

            offer_map = {}

            for tariff in expired_tariffs:
                try:
                    user = tariff.user
                    offer_type = EmailType.DISCOUNT_25_MONTH

                    already_sent = UserOffer.objects.filter(
                        user=user,
                        offer_type=offer_type,
                        start__gte=now - timedelta(days=30)
                    ).exists()

                    if already_sent:
                        continue

                    offer_map.setdefault(offer_type, []).append(user.id)

                except Exception as e:
                    self.stderr.write(
                        f"[OFFER_CHECK] Ошибка при обработке тарифа {tariff.id}, пользователь {tariff.user_id}: {e}"
                    )
                    continue

            for offer_type, user_ids in offer_map.items():
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=user_ids,
                        suggested_time=30*24
                    )
                except Exception as e:
                    self.stderr.write(f"[EMAIL_SEND] Ошибка при отправке email для offer_type={offer_type}: {e}")

            self.stdout.write(self.style.SUCCESS('check_and_offer_30_percent_discount выполнена успешно'))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи предложения 30% скидки: {e}")