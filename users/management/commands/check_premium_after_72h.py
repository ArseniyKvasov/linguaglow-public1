# users/management/commands/check_premium_after_72h.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import CustomUser, UserTariff, UserOffer, EmailType
from users.tasks import send_sale_emails


def _chunked(iterable, size):
    """Простейший чанкер — если нужно отправлять большими партиями."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


class Command(BaseCommand):
    help = (
        "Ищет пользователей с премиум-тарифом, зарегистрированных более 24 часов назад, "
        "и отправляет им специальное письмо, если за последние 7 дней такое письмо не отправлялось."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            cutoff_registered = now - timedelta(hours=24)
            week_ago = now - timedelta(days=7)

            # Ищем пользователей с премиум-тарифом, зарегистрированных более 24 часов назад
            premium_users = (
                CustomUser.objects
                .filter(
                    date_joined__lte=cutoff_registered,
                    tariff__tariff_type=UserTariff.TariffType.PREMIUM,
                    tariff__status=UserTariff.TariffStatus.ACTIVE,
                    is_new=True  # добавляем фильтр по новым пользователям
                )
                .select_related('tariff')
            )

            offer_type = EmailType.PREMIUM_REMINDER  # нужно создать этот тип в EmailType
            to_send_user_ids = []

            for user in premium_users:
                try:
                    # Проверяем, что тариф активен
                    if not user.tariff.is_active():
                        continue

                    # Пропускаем, если письмо уже слали за последние 7 дней
                    already_sent = UserOffer.objects.filter(
                        user=user,
                        offer_type=offer_type,
                        start__gte=week_ago
                    ).exists()

                    if already_sent:
                        user.is_new = False
                        continue

                    to_send_user_ids.append(user.id)

                except Exception as e:
                    self.stderr.write(
                        f"[PREMIUM_PROCESS] Ошибка при обработке пользователя id={getattr(user, 'id', 'n/a')}: {e}"
                    )
                    continue

            if not to_send_user_ids:
                self.stdout.write(self.style.SUCCESS("Нет пользователей для отправки premium_after_72h."))
                return

            # Отправляем пачками
            for chunk in _chunked(to_send_user_ids, 500):
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=chunk,
                        suggested_time=8
                    )
                    self.stdout.write(self.style.SUCCESS(f"Запланирована отправка premium_after_72h для {len(chunk)} пользователей"))
                except Exception as e:
                    self.stderr.write(f"[PREMIUM_SEND] Ошибка при планировании отправки: {e}")

            self.stdout.write(self.style.SUCCESS("premium_after_72h выполнена успешно"))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи premium_after_72h: {e}")