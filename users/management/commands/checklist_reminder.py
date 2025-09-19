# users/management/commands/check_and_remind_onboarding.py

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import UserOnboarding, UserOffer, EmailType
from users.tasks import send_sale_emails


def _chunked(iterable, size):
    """Простейший чанкер — если нужно отправлять большими партиями."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


class Command(BaseCommand):
    help = (
        "Ищет пользователей с незавершённым онбордингом (current_step != generation_feedback), "
        "зарегистрированных более 1 часа назад, и отправляет им onboarding_reminder, "
        "если за последние 7 дней такое письмо не отправлялось."
    )

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            cutoff_registered = now - timedelta(hours=1)
            week_ago = now - timedelta(days=7)

            # Берём все записи онбординга пользователей, которые зарегистрированы >1 часа назад
            onboardings = (
                UserOnboarding.objects
                .select_related("user")
                .filter(user__date_joined__lte=cutoff_registered)
            )

            offer_type = EmailType.CHECKLIST_REMINDER
            to_send_user_ids = []

            for onboarding in onboardings:
                try:
                    user = onboarding.user

                    # Пропускаем, если онбординг завершён (достигнут шаг generation_feedback)
                    if onboarding.get_overall_status():  # True если current_step == "generation_feedback"
                        continue

                    # Пропускаем, если письмо уже слали за последние 7 дней
                    already_sent = UserOffer.objects.filter(
                        user=user,
                        offer_type=offer_type,
                        start__gte=week_ago
                    ).exists()

                    if already_sent:
                        continue

                    to_send_user_ids.append(user.id)

                except Exception as e:
                    self.stderr.write(
                        f"[ONBOARDING_PROCESS] Ошибка при обработке onboarding id={getattr(onboarding, 'id', 'n/a')} "
                        f"user_id={getattr(onboarding, 'user_id', 'n/a')}: {e}"
                    )
                    continue

            if not to_send_user_ids:
                self.stdout.write(self.style.SUCCESS("Нет пользователей для отправки onboarding_reminder."))
                return

            # Отправляем пачками
            for chunk in _chunked(to_send_user_ids, 500):
                try:
                    send_sale_emails.delay(
                        offer_type=offer_type,
                        user_ids=chunk,
                        suggested_time=8
                    )
                    self.stdout.write(self.style.SUCCESS(f"Запланирована отправка onboarding_reminder для {len(chunk)} пользователей"))
                except Exception as e:
                    self.stderr.write(f"[ONBOARDING_SEND] Ошибка при планировании отправки: {e}")

            self.stdout.write(self.style.SUCCESS("onboarding_reminder выполнена успешно"))

        except Exception as e:
            self.stderr.write(f"[CRON_ERROR] Ошибка при выполнении задачи onboarding_reminder: {e}")