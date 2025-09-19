# users/management/commands/check_and_offer_token_discount_to_teachers.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import CustomUser, UserOffer, EmailType, Role
from users.tasks import send_sale_emails


class Command(BaseCommand):
    help = (
        "Проверяет всех пользователей с ролью TEACHER и любым тарифом. "
        "Если у пользователя осталось менее 100 токенов, предлагает купить токены со скидкой: "
        "40%, если за последние полгода не предлагалась, иначе 10%. "
        "Срок действия предложения — 1 день."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            six_months_ago = now - timedelta(days=180)

            teachers = CustomUser.objects.filter(role=Role.TEACHER).select_related('tariff')
            print(teachers)

            offer_map = {}

            for user in teachers:
                try:
                    print(user.token_balance.tokens)
                    if user.token_balance.tokens >= 100:
                        continue

                    sent_40 = UserOffer.objects.filter(
                        user=user,
                        offer_type=EmailType.TOKENS_40_OFF,
                        start__gte=six_months_ago
                    ).exists()

                    offer_type = EmailType.TOKENS_10_OFF if sent_40 else EmailType.TOKENS_40_OFF

                    offer_map.setdefault(offer_type, []).append(user.id)

                except Exception as e:
                    self.stderr.write(f"[TOKEN_DISCOUNT] Ошибка при обработке пользователя {user.id}: {e}")
                    continue

            for offer_type, user_ids in offer_map.items():
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=user_ids,
                        suggested_time=8
                    )
                except Exception as e:
                    self.stderr.write(f"[TOKEN_DISCOUNT_SEND] Ошибка при отправке письма для предложения {offer_type}: {e}")

            self.stdout.write(self.style.SUCCESS('check_and_offer_token_discount_to_teachers выполнена успешно'))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи предложения скидки на токены учителям: {e}")