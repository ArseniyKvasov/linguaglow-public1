# users/management/commands/check_and_offer_50_discount_for_new_free_teachers.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import UserOffer, EmailType, TariffType, CustomUser, Role
from users.tasks import send_sale_emails


class Command(BaseCommand):
    help = (
        "Проверяет пользователей с тарифом FREE и ролью TEACHER. "
        "Если с момента регистрации прошло более 1 часа, и ранее не отправлялось предложение со скидкой 25%, "
        "отправляет такое предложение. Срок действия — 1 день."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            target_time = now - timedelta(days=7)

            users = CustomUser.objects.filter(
                role=Role.TEACHER,
                tariff__tariff_type=TariffType.FREE,
                date_joined__lte=target_time
            ).distinct()

            offer_type = EmailType.UPGRADE_25_OFF
            user_ids_to_offer = []

            for user in users:
                try:
                    already_sent = UserOffer.objects.filter(
                        user=user,
                        offer_type=offer_type,
                        start__gte=now - timedelta(days=30)
                    ).exists()

                    if already_sent:
                        continue

                    user_ids_to_offer.append(user.id)

                except Exception as e:
                    self.stderr.write(f"[OFFER_CHECK] Ошибка при проверке пользователя {user.id}: {e}")
                    continue

            if user_ids_to_offer:
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=user_ids_to_offer,
                        suggested_time=8
                    )
                except Exception as e:
                    self.stderr.write(f"[EMAIL_SEND] Ошибка при отправке email с 50% скидкой: {e}")

            self.stdout.write(self.style.SUCCESS('check_and_offer_25_discount_for_new_free_teachers выполнена успешно'))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи предложения 50% скидки: {e}")