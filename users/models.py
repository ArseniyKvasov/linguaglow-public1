import uuid
from datetime import date, datetime, timedelta
import logging
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from dateutil.relativedelta import relativedelta
from django.db.models import JSONField
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    STUDENT = 'student', 'Ученик'
    TEACHER = 'teacher', 'Учитель'


class Channel(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class CustomUser(AbstractUser):
    class Gender(models.TextChoices):
        FEMALE = "female", _("Женский")
        MALE = "male", _("Мужской")

    class PresentType(models.TextChoices):
        SUBSCRIPTION = "SUBSCRIPTION", _("Подписка")
        TOKENS = "TOKENS", _("Токены")

    email = models.EmailField(
        _('email address'),
        unique=True,  # обычно email делают уникальным, если аутентификация по нему
        blank=False,  # теперь email обязателен
        null=False,
        help_text=_('Email address used for login and account management.')
    )

    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )

    # Убрано поле email_confirmed
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    teaching_role = models.CharField(max_length=50, default="undefined")
    allow_emails = models.BooleanField(default=True)
    consent = models.BooleanField(default=False)
    used_storage = models.BigIntegerField(default=0)
    ref_source = models.ForeignKey(Channel, blank=True, null=True, on_delete=models.SET_NULL)
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        default=Gender.FEMALE,
        help_text=_("Пол пользователя"),
    )
    present_type = models.CharField(
        max_length=12,
        choices=PresentType.choices,
        default=PresentType.SUBSCRIPTION,
        help_text=_("Тип подарка для пользователя"),
    )
    is_new = models.BooleanField(default=True, help_text=_("Флаг нового пользователя"))

    # Аутентификация через username (оставим стандартное поле)
    USERNAME_FIELD = 'username'  # Для Django важное поле, в базе уникальное
    REQUIRED_FIELDS = ['email']  # Убираем пустоту, теперь email обязателен при создании через createsuperuser и др.

    def __str__(self):
        return self.username

    def get_gender(self):
        """
        Возвращает человекочитаемое значение пола пользователя.
        """
        return self.get_gender_display()

    def get_present_type(self):
        """Возвращает человекочитаемое значение типа подарка."""
        return self.get_present_type_display()

    def update_used_storage(self, additional_size):
        """
        Обновляет информацию о занятом объеме памяти пользователем.
        Гарантирует, что значение used_storage не будет меньше нуля.
        """
        if not isinstance(additional_size, (int, float)):
            raise TypeError("additional_size must be a number")

        new_storage = self.used_storage + additional_size
        final_storage = max(new_storage, 0)

        self.used_storage = final_storage
        self.save()

class EmailConfirmation(models.Model):
    email = models.EmailField()
    username = models.CharField(max_length=150)
    password = models.CharField(max_length=128)  # захеширован
    role = models.CharField(max_length=20)  # TEACHER или STUDENT
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)

class PasswordResetCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)

    def __str__(self):
        return f"{self.user.email} - {self.code}"


User = get_user_model()


class TariffType(models.TextChoices):
    FREE = 'free', 'Бесплатный'
    BASIC = 'basic', 'Базовый'
    PREMIUM = 'premium', 'Премиум'
    MAXIMUM = 'maximum', 'Максимум'

class TariffStatus(models.TextChoices):
    ACTIVE = 'active', 'Активный'
    UNPAID = 'unpaid', 'Неоплаченный'

class UserTariff(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='tariff')
    tariff_type = models.CharField(
        max_length=20,
        choices=TariffType.choices,
        default=TariffType.FREE
    )
    status = models.CharField(
        max_length=20,
        choices=TariffStatus.choices,
        default=TariffStatus.ACTIVE
    )
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    # новые поля для расписания сбросов и пополнений токенов
    reset_dates = JSONField(
        null=True,
        blank=True,
        help_text='Список строк дат (дней без времени), когда токены будут обнуляться и начисляться заново'
    )
    price_month = models.PositiveIntegerField(
        default=0,
        help_text='Оплаченная стоимость тарифа за месяц'
    )
    months_left = models.PositiveIntegerField(
        default=0,
        help_text='Оставшееся количество месяцев действия тарифа'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        if self.status != TariffStatus.ACTIVE:
            return False
        if self.end_date and self.end_date < timezone.now():
            return False
        return True

    def __str__(self):
        return f"{self.user.username}: {self.get_tariff_type_display()} ({self.get_status_display()})"

    def get_next_reset_date_display(self):
        if not self.reset_dates:
            return None

        today = date.today()

        try:
            # преобразуем строки в даты
            dates = [
                datetime.strptime(d, "%Y-%m-%d").date()
                for d in self.reset_dates
            ]
            # ищем ближайшую дату в будущем
            future_dates = sorted(d for d in dates if d > today)
            if future_dates:
                return future_dates[0].strftime("%d.%m")
        except (ValueError, TypeError):
            pass

        return None

class UserTokenBalance(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='token_balance')
    tariff_tokens = models.IntegerField(default=0, verbose_name='Токены тарифа')
    extra_tokens = models.IntegerField(default=0, verbose_name='Докупленные токены')
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def tokens(self):
        return self.tariff_tokens + self.extra_tokens

    def __str__(self):
        return f"{self.user.username} — {self.tokens} токенов (тариф: {self.tariff_tokens}, доп: {self.extra_tokens})"

class Payment(models.Model):
    class PaymentType(models.TextChoices):
        TARIFF     = 'tariff', 'Тариф'
        TOKEN_PACK = 'token_pack', 'Пакет токенов'

    class Status(models.TextChoices):
        PENDING   = 'pending',   'Ожидает оплаты'
        COMPLETED = 'completed', 'Оплачено'
        FAILED    = 'failed',    'Не удалось'

    class TariffDuration(models.TextChoices):
        MONTH = 'month', '1 месяц'
        SIX_MONTH = '6mo', '6 месяцев'
        YEAR = 'year', '12 месяцев'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    payment_type = models.CharField(
        max_length=20,
        choices=PaymentType.choices
    )

    tariff_type = models.CharField(
        max_length=20,
        choices=(
            ('free', 'Бесплатный'),
            ('basic', 'Базовый'),
            ('premium', 'Премиум'),
            ('maximum', 'Максимум'),
        ),
        blank=True,
        null=True,
        help_text='Тип тарифа, если payment_type=tariff'
    )
    tariff_duration = models.CharField(
        max_length=10,
        choices=TariffDuration.choices,
        blank=True,
        null=True,
        help_text='Продолжительность тарифа (месяц/6мес/год)'
    )

    token_amount = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Количество токенов в пакете, если payment_type=token_pack'
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    full_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(
        max_length=5,
        default='RUB'
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='ID платежа от платёжного провайдера'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Время подтверждённой оплаты'
    )

    period_start = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Начало периода тарифа'
    )
    period_end = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Окончание периода тарифа'
    )

    channel = models.ForeignKey(
        Channel,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        help_text="Канал, через который была сделана покупка"
    )

    def save(self, *args, **kwargs):
        # при создании платежа автоматически подтягиваем канал пользователя
        if not self.channel and self.user.ref_source:
            self.channel = self.user.ref_source
        super().save(*args, **kwargs)

    def mark_completed(self, transaction_id: str):
        self.status = self.Status.COMPLETED
        self.transaction_id = transaction_id
        self.paid_at = timezone.now()

        if self.payment_type == self.PaymentType.TARIFF:
            now = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            self.period_start = now

            # определим окончание тарифа по длительности
            if self.tariff_duration == self.TariffDuration.MONTH:
                self.period_end = now + relativedelta(months=1)
            elif self.tariff_duration == self.TariffDuration.SIX_MONTH:
                self.period_end = now + relativedelta(months=6)
            elif self.tariff_duration == self.TariffDuration.YEAR:
                self.period_end = now + relativedelta(years=1)

        self.save()

    def __str__(self):
        return (
            f"Payment #{self.pk} | {self.user.username} | "
            f"{self.get_payment_type_display()} | {self.amount}{self.currency} | "
            f"{self.get_status_display()}"
        )

class Notification(models.Model):
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Ссылка для кнопки «Подробнее» (необязательно)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    # Новое поле: список ролей, которым адресовано уведомление
    target_roles = ArrayField(
        models.CharField(max_length=20, choices=Role.choices),
        default=list,
        help_text="Роли пользователей, которым будет показано уведомление"
    )

class UserNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    is_hidden = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'notification')  # Чтобы не было дублей



class EmailType(models.TextChoices):
    # Скидки и акции тарифов
    DISCOUNT_20 = 'discount_20', 'Скидка 20% на продление тарифа'
    DISCOUNT_10 = 'discount_10', 'Скидка 10% на продление тарифа'
    GIFT_2000_TOKENS = 'gift_2000_tokens', '2000 токенов в подарок'
    GIFT_1000_TOKENS = 'gift_1000_tokens', '1000 токенов в подарок'
    DISCOUNT_25_MONTH = 'discount_25_month', 'Скидка 25% на месяц'
    TOKENS_40_OFF = 'tokens_40_off', 'Токены со скидкой 40%'
    TOKENS_10_OFF = 'tokens_10_off', 'Токены со скидкой 10%'
    UPGRADE_25_OFF = 'upgrade_25_off', 'Переход с бесплатного тарифа со скидкой 25%'

    # Системные письма
    WELCOME = 'welcome', 'Приветственное сообщение'

    # Напоминания о продлении без скидки
    REMINDER_RENEW_BASIC = 'reminder_renew_basic', 'Напоминание о продлении тарифа Базовый'
    REMINDER_RENEW_PREMIUM = 'reminder_renew_premium', 'Напоминание о продлении тарифа Премиум'
    REMINDER_RENEW_MAXIMUM = 'reminder_renew_maximum', 'Напоминание о продлении тарифа Максимум'

    # Покупка тарифов
    PURCHASE_BASIC = 'purchase_basic', 'Покупка тарифа Базовый'
    PURCHASE_PREMIUM = 'purchase_premium', 'Покупка тарифа Премиум'
    PURCHASE_MAXIMUM = 'purchase_maximum', 'Покупка тарифа Максимум'

    # Продление тарифов
    RENEW_BASIC = 'renew_basic', 'Продление тарифа Базовый'
    RENEW_PREMIUM = 'renew_premium', 'Продление тарифа Премиум'
    RENEW_MAXIMUM = 'renew_maximum', 'Продление тарифа Максимум'

    # Общее
    GENERIC = 'generic', 'Обычное письмо'
    CHECKLIST_REMINDER = 'checklist_reminder', 'Напоминание о чек-листе'
    PREMIUM_REMINDER = 'premium_reminder', 'Напоминание о наличии премиума'

SUBSCRIPTION_OFFERS = {
    EmailType.DISCOUNT_20,
    EmailType.DISCOUNT_10,
    EmailType.GIFT_2000_TOKENS,
    EmailType.GIFT_1000_TOKENS,
    EmailType.DISCOUNT_25_MONTH,
    EmailType.UPGRADE_25_OFF,
    EmailType.REMINDER_RENEW_BASIC,
    EmailType.REMINDER_RENEW_PREMIUM,
    EmailType.REMINDER_RENEW_MAXIMUM,
}

TOKENS_OFFERS = {
    EmailType.TOKENS_40_OFF,
    EmailType.TOKENS_10_OFF,
}

class EmailTemplate(models.Model):
    title = models.CharField(max_length=255)
    html_content = models.TextField()
    type = models.CharField(
        max_length=32,
        choices=EmailType.choices,
        default=EmailType.GENERIC
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.get_type_display()})"

class OfferCategory(models.TextChoices):
    SUBSCRIPTION = 'subscription', 'Подписка'
    TOKENS = 'tokens', 'Токены'
    OTHER = 'other', 'Другое'

class UserOffer(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    offer_type = models.CharField(max_length=32, choices=EmailType.choices)
    category = models.CharField(max_length=16, choices=OfferCategory.choices, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Предложение пользователю'
        verbose_name_plural = 'Предложения пользователям'
        ordering = ['-start']

    def __str__(self):
        return (
            f"{self.user} — {self.get_offer_type_display()} "
            f"[{self.get_category_display()}] ({self.start.date()} - {self.end.date()})"
        )

    def save(self, *args, **kwargs):
        if not self.category:
            self.category = self.detect_category(self.offer_type)
        super().save(*args, **kwargs)

    @staticmethod
    def detect_category(offer_type):
        if offer_type in SUBSCRIPTION_OFFERS:
            return OfferCategory.SUBSCRIPTION
        elif offer_type in TOKENS_OFFERS:
            return OfferCategory.TOKENS
        else:
            return OfferCategory.OTHER


class UserOnboarding(models.Model):
    STEP_CHOICES = [
        ("hello", "Hello"),
        ("segment", "Segment"),
        ("generation_waiting", "Generation waiting"),
        ("generation_result", "Generation result"),
        ("generation_feedback", "Generation feedback"),
        ("incorrect", "Generation incorrect"),
        ("done", "Generation done"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="starts"
    )
    generation_id = models.CharField(max_length=255, null=True, blank=True)
    current_step = models.CharField(
        max_length=32,
        choices=STEP_CHOICES,
        default="hello",
        null=True,
        blank=True
    )
    lesson_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.user} – step: {self.current_step}"

    def get_overall_status(self) -> bool:
        """
        Возвращает True, если все задачи выполнены.
        Условно считаем, что «все задачи выполнены», когда шаг == generation_feedback.
        Во всех остальных случаях — False.
        """
        return self.current_step == "done"



class UserMetrics(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="metrics"
    )

    # --- Счётчики ---
    pdf_downloaded_counter = models.PositiveIntegerField(default=0)
    ai_requests_counter = models.PositiveIntegerField(default=0)

    # --- Метрики по активностям ---
    tasks_generated_counter = models.PositiveIntegerField(default=0)     # задания
    sections_generated_counter = models.PositiveIntegerField(default=0)  # разделы
    lessons_generated_counter = models.PositiveIntegerField(default=0)   # уроки

    # --- Retention ---
    first_activity_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)

    def update_activity(self):
        """Фиксируем активность пользователя (первая + последняя)"""
        now = timezone.now()
        if not self.first_activity_at:
            self.first_activity_at = now
        self.last_activity_at = now
        self.save(update_fields=["first_activity_at", "last_activity_at"])

    def retention_status(self):
        """
        Проверяем retention: вернулся ли пользователь на D1, D3, D7
        Возвращает dict с True/False
        """
        if not self.first_activity_at or not self.last_activity_at:
            return {"D1": False, "D3": False, "D7": False}

        first_date = self.first_activity_at.date()
        last_date = self.last_activity_at.date()

        return {
            "D1": last_date >= first_date + timedelta(days=1),
            "D3": last_date >= first_date + timedelta(days=3),
            "D7": last_date >= first_date + timedelta(days=7),
        }

    def __str__(self):
        return f"Metrics for {self.user}"

class Level(models.Model):
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Textbook(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Grade(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class TelegramMetrics(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_metrics'
    )
    pdf_downloaded = models.PositiveIntegerField(default=0)
    generation_requests = models.PositiveIntegerField(default=0)

    telegram_id = models.BigIntegerField(unique=True)  # id пользователя в TG
    telegram_username = models.CharField(max_length=255, null=True, blank=True)

    grade = models.ManyToManyField(Grade, blank=True)
    level = models.ManyToManyField(Level, blank=True)
    textbooks = models.ManyToManyField(Textbook, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        user_str = self.user.username if self.user else "Аноним"
        return f"Metrics for {user_str} | PDFs: {self.pdf_downloaded}, Requests: {self.generation_requests}"

class TelegramAuthToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_tokens"
    )
    token = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def is_valid(self):
        # токен живёт 15 минут
        return not self.used and self.created_at >= timezone.now() - timedelta(minutes=15)

    def __str__(self):
        return f"Token for {self.user.email} (used={self.used})"



class Application(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    name = models.CharField(max_length=255, blank=True, null=True)
    contact = models.CharField(max_length=255)

    ROLE_CHOICES = [
        ("tutor", "Частный репетитор"),
        ("school_teacher", "Школьный учитель"),
        ("university_teacher", "Преподаватель вуза"),
        ("other", "Другое"),
    ]
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)

    subject = models.CharField(max_length=50)

    WILLINGNESS_CHOICES = [
        ("yes", "Да"),
        ("maybeyes", "Скорее да"),
        ("maybe", "Скорее нет"),
        ("no", "Точно нет"),
    ]

    tg_homework = models.CharField(
        max_length=10,
        choices=WILLINGNESS_CHOICES,
        help_text=""
    )

    ai_checking = models.CharField(
        max_length=10,
        choices=WILLINGNESS_CHOICES,
        help_text=""
    )

    workflow = models.TextField(
        blank=True,
        null=True,
        help_text=""
    )

    tester = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.contact} ({self.role})"

class ArseniyApplication(models.Model):
    child_name = models.CharField("Имя ребёнка", max_length=100)
    grade = models.CharField("Класс", max_length=20)
    phone = models.CharField("Телефон", max_length=30)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    def __str__(self):
        return f"{self.child_name} ({self.grade})"