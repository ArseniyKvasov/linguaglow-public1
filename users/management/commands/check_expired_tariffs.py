# users/management/commands/check_and_remind_expired_tariffs.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import UserTariff, EmailType, UserOffer, TariffType
from users.tasks import send_sale_emails


class Command(BaseCommand):
    help = (
        "Проверяет пользователей с тарифами BASIC, PREMIUM, MAXIMUM, "
        "у которых тариф закончился за последние сутки, и отправляет напоминание о продлении. "
        "Если напоминание уже отправлялось за последние 24 часа, повторно не отправляется."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            yesterday = now - timedelta(days=2)

            expired_tariffs = UserTariff.objects.filter(
                tariff_type__in=[TariffType.BASIC, TariffType.PREMIUM, TariffType.MAXIMUM],
                end_date__range=(yesterday, now),
            )
            print(expired_tariffs)

            reminder_type_map = {
                TariffType.BASIC: EmailType.REMINDER_RENEW_BASIC,
                TariffType.PREMIUM: EmailType.REMINDER_RENEW_PREMIUM,
                TariffType.MAXIMUM: EmailType.REMINDER_RENEW_MAXIMUM,
            }

            offer_map = {}

            for tariff in expired_tariffs:
                print(tariff)
                try:
                    user = tariff.user
                    print(user)
                    offer_type = reminder_type_map.get(tariff.tariff_type)

                    if not offer_type:
                        continue
                    """
                    already_sent = UserOffer.objects.filter(
                        user=user,
                        offer_type=offer_type,
                        start__gte=yesterday
                    ).exists()
                    """
                    already_sent = False
                    if already_sent:
                        continue

                    offer_map.setdefault(offer_type, []).append(user.id)

                except Exception as e:
                    self.stderr.write(f"[REMINDER_CHECK] Ошибка при обработке тарифа {tariff.id}, пользователь {tariff.user_id}: {e}")
                    continue

            for offer_type, user_ids in offer_map.items():
                print(user_ids)
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=user_ids,
                        suggested_time=8
                    )
                except Exception as e:
                    self.stderr.write(f"[REMINDER_SEND] Ошибка при отправке письма для предложения {offer_type}: {e}")

            self.stdout.write(self.style.SUCCESS('check_and_remind_expired_tariffs выполнена успешно'))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи напоминания об истечении тарифа: {e}")