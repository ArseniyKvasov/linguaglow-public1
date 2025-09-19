# management/commands/reset_tariff_tokens.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from users.models import UserTokenBalance, UserTariff, TariffStatus
from datetime import date

class Command(BaseCommand):
    help = 'Ежедневно сбрасывает токены в дни из reset_dates, начисляет новые и деактивирует просроченные тарифы'

    def handle(self, *args, **options):
        now = timezone.now()
        today = now.date()
        reset_count = 0
        deactivated = 0

        for user_tariff in UserTariff.objects.select_related('user'):
            user = user_tariff.user
            balance, _ = UserTokenBalance.objects.get_or_create(user=user)

            # 1) Деактивация просроченных тарифов
            if user_tariff.end_date and user_tariff.end_date < now:
                if user_tariff.status != TariffStatus.UNPAID:
                    user_tariff.status = TariffStatus.UNPAID
                    user_tariff.reset_dates = None  # сбрасываем расписание
                    user_tariff.save(update_fields=['status', 'reset_dates', 'updated_at'])
                    deactivated += 1

                # Сбрасываем токены у неактивного тарифа
                balance.tariff_tokens = 0
                balance.save(update_fields=['tariff_tokens', 'updated_at'])
                continue

            # 2) Сброс и начисление токенов в день из reset_dates (только по дате)
            if user_tariff.reset_dates:
                for d_str in user_tariff.reset_dates:
                    try:
                        reset_day = date.fromisoformat(d_str)
                    except ValueError:
                        # некорректная строка — пропускаем
                        continue

                    if reset_day == today:
                        # Сбрасываем и начисляем новые токены
                        limit = settings.TARIFFS[user_tariff.tariff_type]['token_limit']
                        balance.tariff_tokens = limit
                        balance.save(update_fields=['tariff_tokens', 'updated_at'])

                        # Уменьшаем months_left, если поле есть
                        if hasattr(user_tariff, 'months_left'):
                            new_months_left = max(user_tariff.months_left - 1, 0)
                            if new_months_left != user_tariff.months_left:
                                user_tariff.months_left = new_months_left
                                user_tariff.save(update_fields=['months_left', 'updated_at'])

                        reset_count += 1
                        break  # нашли сегодня — выходим из цикла по датам

            # 3) Статус остаётся активным, дополнительная логика здесь не нужна
            # if user_tariff.is_active():
            #     pass

        self.stdout.write(self.style.SUCCESS(
            f'✅ Сброшено и начислено токенов: {reset_count} | ❌ Деактивовано тарифов: {deactivated}'
        ))

