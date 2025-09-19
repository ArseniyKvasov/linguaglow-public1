# users/management/commands/check_and_offer_discount_after_expiry.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from users.models import UserTariff, EmailType, UserOffer, TariffType
from users.tasks import send_sale_emails

User = get_user_model()

class Command(BaseCommand):
    help = (
        "Ежедневно проверяет пользователей с истекшими 48-72 часами тарифами BASIC, PREMIUM, MAXIMUM. "
        "Если за последние 6 месяцев не предлагалась скидка 20%, отправляет письмо с 20%, иначе с 10%. "
        "Каждое письмо действует сутки."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            window_start = now - timedelta(hours=72)
            window_end = now - timedelta(hours=48)
            six_months_ago = now - timedelta(days=180)

            target_tariff_types = [
                TariffType.BASIC,
                TariffType.PREMIUM,
                TariffType.MAXIMUM
            ]

            expired_tariffs = UserTariff.objects.filter(
                tariff_type__in=target_tariff_types,
                end_date__range=(window_start, window_end)
            )

            discount_20_type = EmailType.DISCOUNT_20
            discount_10_type = EmailType.DISCOUNT_10

            user_ids_for_20 = []
            user_ids_for_10 = []

            for tariff in expired_tariffs:
                try:
                    user = tariff.user

                    # Проверяем, есть ли у пользователя активный тариф из нужных
                    has_active_tariff = UserTariff.objects.filter(
                        user=user,
                        tariff_type__in=target_tariff_types,
                        end_date__gt=now
                    ).exists()

                    if has_active_tariff:
                        continue

                    # Проверяем, предлагали ли скидку 20% за последние 6 месяцев
                    was_discount_20_offered = UserOffer.objects.filter(
                        user=user,
                        offer_type=discount_20_type,
                        start__gte=six_months_ago
                    ).exists()

                    if was_discount_20_offered:
                        user_ids_for_10.append(user.id)
                    else:
                        user_ids_for_20.append(user.id)

                except Exception as e:
                    self.stderr.write(
                        f"[OFFER_CHECK] Ошибка при обработке тарифа {tariff.id}, пользователь {tariff.user_id}: {e}"
                    )
                    continue

            if user_ids_for_20:
                try:
                    send_sale_emails.delay(
                        offer_type=discount_20_type,
                        user_ids=user_ids_for_20,
                        suggested_time=8
                    )
                except Exception as e:
                    self.stderr.write(f"[EMAIL_SEND] Ошибка при отправке email с 20% скидкой: {e}")

            if user_ids_for_10:
                try:
                    send_sale_emails.delay(
                        offer_type=discount_10_type,
                        user_ids=user_ids_for_10,
                        suggested_time=8
                    )
                except Exception as e:
                    self.stderr.write(f"[EMAIL_SEND] Ошибка при отправке email с 10% скидкой: {e}")

            self.stdout.write(self.style.SUCCESS('check_and_offer_discount_after_expiry выполнена успешно'))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи предложения скидок по тарифам: {e}")