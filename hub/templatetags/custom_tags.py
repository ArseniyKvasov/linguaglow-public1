
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from django import template
from django.conf import settings
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils import timezone
from hub.models import LessonPublicData, Lesson, Course
# Импорт моделей — оставил как были в проекте
from users.models import UserOffer, EmailType, UserTariff, TOKENS_OFFERS, SUBSCRIPTION_OFFERS, OfferCategory, TariffType, UserOnboarding

register = template.Library()

@register.filter
def dict_get(d, key):
    return d.get(key, [])

def _clamp(value: float, lo: float, hi: float) -> float:
    """
    Ограничить дробное значение в диапазоне [lo, hi].
    """
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _calc_subscription_discounts(base_fraction: float) -> Dict[str, float]:
    print("BASE FRACTION: ", base_fraction)
    """
    Рассчитывает скидки на основе базовой дробной скидки:
      - month = base_fraction
      - 6mo   = base_fraction + 0.05, затем clamp в [0.15, 0.35]
      - year  = base_fraction + 0.10, затем clamp в [0.30, 0.45]
    Возвращает словарь с дробными значениями (например 0.2).
    """
    month = base_fraction
    six_month = _clamp(base_fraction + 0.05, 0.15, 0.35)
    year = _clamp(base_fraction + 0.15, 0.30, 0.40)
    print("SIX MONTH: ", six_month)
    print("YEAR: ", year)
    return {
        'sub_month': round(month, 3),
        'sub_6mo': round(six_month, 3),
        'sub_year': round(year, 3),
    }


def get_user_tariff_discounts(user) -> Dict[str, Any]:
    """
    Берёт последний (most recent) активный оффер пользователя и возвращает
    соответствующие значения.

    Возвращаемая структура:
      {
        'sub_month': float,
        'sub_6mo': float,
        'sub_year': float,
        'tokens': int,
        'marketing_type': Optional[str],
        'end_time': Optional[int],  # секунды до окончания
      }

    Правила:
      - Для незарегистрированного пользователя показываем публичную акцию:
          sub_6mo = 0.15 (15%), sub_year = 0.30 (30%)
      - Для зарегистрированного пользователя ищем самый новый активный подписочный оффер.
      - Если оффер токеновый (GIFT_* или имеет поле tokens) — возвращаем tokens.
      - Если подписочный — определяем base (25/20/10) и считаем sub_* через _calc_subscription_discounts.
      - Скидки не суммируются — учитывается только выбранный оффер.
    """
    now = timezone.now()

    # По умолчанию — никаких персональных скидок
    result: Dict[str, Any] = {
        'sub_month': 0.0,
        'sub_6mo': 0.0,
        'sub_year': 0.0,
        'tokens': 0,
        'marketing_type': None,
        'end_time': None,
    }

    # Для гостей показываем публичную акцию: 15% за 6 месяцев и 30% за год
    if not user or not getattr(user, 'is_authenticated', False):
        result['sub_6mo'] = 0.15
        result['sub_year'] = 0.30
        result['marketing_type'] = ''
        result['end_time'] = None
        return result

    # Для аутентифицированного пользователя — ищем активный подписочный оффер
    offer = (
        UserOffer.objects.filter(
            user=user,
            start__lte=now,
            end__gte=now,
            is_used=False,
            category=OfferCategory.SUBSCRIPTION
        )
        .order_by('-start')
        .first()
    )

    base = 0.0
    remaining = None

    if offer is not None:
        remaining = max(int((offer.end - now).total_seconds()), 0)

        # Если оффер явно токеновый или содержит поле tokens — возвращаем tokens
        if offer.offer_type in {EmailType.GIFT_1000_TOKENS, EmailType.GIFT_2000_TOKENS} or getattr(offer, 'tokens', 0):
            result['tokens'] = int(getattr(offer, 'tokens', 0) or 0)
            result['marketing_type'] = 'Дополнительные токены в подарок'
            result['end_time'] = remaining

        # Если подписочный оффер — определяем базовую скидку по имени/типу
        elif offer.offer_type in SUBSCRIPTION_OFFERS:
            typ = str(offer.offer_type)
            if '25' in typ:
                base = 0.25
            elif '20' in typ:
                base = 0.20
            elif '10' in typ:
                base = 0.10
            else:
                base = 0.0

    # Рассчитываем скидки по периодам из базовой скидки (если есть)
    subs = _calc_subscription_discounts(base)
    result.update(subs)

    if base > 0:
        result['marketing_type'] = 'Персональная скидка'
        result['end_time'] = remaining

    return result

def get_user_token_discounts(user, full_price: float) -> Dict[str, Any]:
    """
    Возвращает данные о скидке на покупку токенов для пользователя.
    """
    result: Dict[str, Any] = {
        'full_price': round(full_price, 2),
        'discounted_price': round(full_price, 2),
        'discount_percent': 0,
        'marketing_text': None,
        'end_time': None,
    }

    # если пользователь не авторизован — сразу отдаём full_price
    if not user or not getattr(user, "is_authenticated", False):
        return result

    now = timezone.now()

    offers = (
        UserOffer.objects.filter(
            user=user,
            start__lte=now,
            end__gte=now,
            is_used=False,
            category=OfferCategory.TOKENS
        )
        .order_by('-start')
    )

    offer = None
    for discount_type in (EmailType.TOKENS_40_OFF, EmailType.TOKENS_10_OFF):
        candidate = offers.filter(offer_type=discount_type).first()
        if candidate:
            offer = candidate
            break

    if not offer:
        return result

    if offer.offer_type == EmailType.TOKENS_40_OFF:
        discount_percent = 40
    elif offer.offer_type == EmailType.TOKENS_10_OFF:
        discount_percent = 10
    else:
        discount_percent = 0

    if discount_percent > 0:
        discounted_price = full_price * (1 - discount_percent / 100)
        result['discount_percent'] = discount_percent
        result['discounted_price'] = round(discounted_price, 2)
        result['marketing_text'] = f"Персональная скидка {discount_percent}%"
        result['end_time'] = max(int((offer.end - now).total_seconds()), 0)

    return result


def apply_discount(value: Optional[float], discount_fraction: float) -> int:
    """
    Применяет дробную скидку к value и возвращает округлённое целое значение в рублях.
    Если value is None — возвращает 0.
    """
    if value is None:
        return 0
    val = Decimal(str(value))
    factor = Decimal('1') - Decimal(str(discount_fraction or 0))
    result = (val * factor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(result)


def _month_from_total(total: int, months: int) -> int:
    """
    Получить месячную цену (целое рубли) из суммарной цены total за months месяцев.
    Делим через Decimal и округляем HALF_UP до целого.
    """
    if not total or months <= 0:
        return 0
    month_val = (Decimal(total) / Decimal(months)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(month_val)


def recount_tariff_prices(user, discounts: Optional[Dict[str, Any]] = None, consider_prepaid = True) -> Dict[str, Dict[str, Any]]:
    """
    Возвращает словарь тарифов с применёнными скидками и дополнительными полями:
      - full_price: исходная месячная цена (без скидки)
      - price_month: месячная цена с персональной скидкой (не менее 1 рубля)
      - price_6mo: сумма за 6 месяцев с соответствующей скидкой (не менее 1 рубля)
      - price_6mo_month: эквивалент месячной цены при оплате 6 месяцев
      - price_year: сумма за 12 месяцев с соответствующей скидкой (не менее 1 рубля)
      - price_year_month: эквивалент месячной цены при оплате года
      - marketing_type, end_time: общие для всех тарифов (берутся из discounts)

    Если у пользователя есть активный платный тариф с months_left >= 1,
    то вычитаем из цены КАЖДОГО ТАРИФА, КРОМЕ ТЕКУЩЕГО АКТИВНОГО, сумму: price_month * months_left.
    Минимальная цена - 1 рубль.
    """
    if discounts is None:
        discounts = get_user_tariff_discounts(user)

    result: Dict[str, Dict[str, Any]] = {}

    # Проверяем активный платный тариф
    active_tariff = None
    active_tariff_name = None
    if user and hasattr(user, 'tariff'):
        try:
            ut = user.tariff
            if ut.is_active() and ut.tariff_type != TariffType.FREE and ut.months_left >= 1:
                active_tariff = ut
                active_tariff_name = ut.tariff_type  # сохраняем имя текущего тарифа
        except UserTariff.DoesNotExist:
            active_tariff = None
            active_tariff_name = None

    # Вычитаемая сумма
    deduction = 0.0
    if active_tariff and consider_prepaid:
        deduction = float(active_tariff.price_month) * active_tariff.months_left

    for name, data in settings.TARIFFS.items():
        new_data = data.copy()
        base_month = data.get('price_month')  # исходная месячная цена (число или None)
        base_month_val = float(base_month) if base_month else 0.0
        new_data['full_price'] = base_month_val

        # Месячная цена с персональной скидкой
        price_month = apply_discount(base_month_val, discounts.get('sub_month', 0.0))

        # Вычитаем deduction только если это НЕ текущий активный тариф
        if name == active_tariff_name:
            # Для текущего тарифа НЕ вычитаем deduction
            price_month_adj = price_month
            total_6mo_adj = apply_discount(base_month_val * 6, discounts.get('sub_6mo', 0.0))
            total_year_adj = apply_discount(base_month_val * 12, discounts.get('sub_year', 0.0))
        else:
            # Для всех остальных тарифов вычитаем deduction (минимум 1 рубль)
            price_month_adj = max(price_month - deduction, 1.0)  # минимум 1 рубль
            total_6mo = apply_discount(base_month_val * 6, discounts.get('sub_6mo', 0.0))
            total_6mo_adj = max(total_6mo - deduction, 1.0)  # минимум 1 рубль
            total_year = apply_discount(base_month_val * 12, discounts.get('sub_year', 0.0))
            total_year_adj = max(total_year - deduction, 1.0)  # минимум 1 рубль

        new_data['price_month'] = price_month_adj
        new_data['price_6mo'] = total_6mo_adj
        new_data['price_year'] = total_year_adj

        # Рассчитываем эквивалентные месячные цены (также минимум 1 рубль за период)
        new_data['price_6mo_month'] = max(total_6mo_adj / 6, 1.0) if total_6mo_adj > 0 else 1.0
        new_data['price_year_month'] = max(total_year_adj / 12, 1.0) if total_year_adj > 0 else 1.0

        new_data['marketing_type'] = discounts.get('marketing_type')
        new_data['end_time'] = discounts.get('end_time')

        result[name] = new_data

    return result

def recount_token_prices(user) -> list:
    """
    Возвращает список пакетов токенов с учётом персональных скидок.
    Использует get_user_token_discounts для расчёта цен.

    Формат:
      [
        {
          'amount': int,              # количество токенов
          'price': int,               # цена со скидкой
          'full_price': int,          # цена без скидки
          'marketing_text': Optional[str],
          'end_time': Optional[int],
        },
        ...
      ]
    """
    packs = []
    for pack in settings.TOKEN_PACKS:
        full_price = pack.get('price')
        token_discount = get_user_token_discounts(user, full_price)

        packs.append({
            'amount': pack.get('amount'),
            'price': int(token_discount['discounted_price']),
            'full_price': int(token_discount['full_price']),
            'marketing_text': token_discount['marketing_text'],
            'end_time': token_discount['end_time'],
        })

    return packs




@register.inclusion_tag('home/pricing_section.html', takes_context=True)
def render_pricing_section(context):
    request: HttpRequest = context['request']
    user = getattr(request, 'user', None)

    plans_meta = [
        {'key': 'basic', 'title': 'Базовый'},
        {'key': 'premium', 'title': 'Премиум'},
        {'key': 'maximum', 'title': 'Максимум'},
    ]

    discounts = get_user_tariff_discounts(user)
    tariffs = recount_tariff_prices(user, discounts)

    used_gb = 0.0
    if user and getattr(user, 'is_authenticated', False):
        used_bytes = getattr(user, 'used_storage', 0) or 0
        used_gb = used_bytes / 1024 ** 3

    current_tariff = None
    is_current_active = False
    current_months_left = 0
    if user and getattr(user, 'is_authenticated', False):
        try:
            ut = user.tariff
            current_tariff = ut.tariff_type
            is_current_active = ut.is_active()
            current_months_left = getattr(ut, 'months_left', 0) or 0
        except Exception:
            current_tariff = None
            is_current_active = False
            current_months_left = 0

    plans = []
    for meta in plans_meta:
        key = meta['key']
        cfg = tariffs.get(key, {})

        plan = {
            'key': key,
            'title': meta['title'],
            'access': cfg.get('virtual_class', False),
            'tokens': cfg.get('token_limit', 0),
            'memory': cfg.get('memory_gb', 0),
            'classes': (cfg.get('token_limit', 0) // 50) if cfg.get('token_limit') else 0,
            'full_price': cfg.get('full_price', 0),
            'price_month': cfg.get('price_month', 0),
            'price_6mo': cfg.get('price_6mo', 0),
            'price_year': cfg.get('price_year', 0),
            'marketing_type': cfg.get('marketing_type'),
            'end_time': cfg.get('end_time'),
            'gift_tokens': cfg.get('token_limit') if cfg.get('marketing_type') == 'Дополнительные токены' else 0,
            'sales': {},
            'period_statuses': {
                'month': 'available',
                '6mo': 'available',
                'year': 'available',
            }
        }

        try:
            full = float(plan['full_price']) if plan['full_price'] else 0.0
            if full:
                pm = float(plan['price_month']) if plan['price_month'] is not None else full
                plan['sales']['month'] = round(100 * (1 - pm / full))
                p6_total = float(plan.get('price_6mo')) if plan.get('price_6mo') is not None else full * 6
                plan['sales']['6mo'] = round(100 * (1 - (p6_total / (full * 6))))
                py_total = float(plan.get('price_year')) if plan.get('price_year') is not None else full * 12
                plan['sales']['year'] = round(100 * (1 - (py_total / (full * 12))))
        except Exception:
            plan['sales'] = {}

        if plan['memory'] < used_gb:
            plan['period_statuses'] = {'month': 'unavailable', '6mo': 'unavailable', 'year': 'unavailable'}
            plan['status'] = 'unavailable'
            plans.append(plan)
            continue

        if key == current_tariff:
            days_left = getattr(ut, 'days_left', None)
            if days_left is None and getattr(ut, 'end_date', None):
                days_left = (ut.end_date.date() - timezone.now().date()).days

            if days_left is not None and days_left < 6:
                plan['period_statuses'] = {'month': 'renew', '6mo': 'renew', 'year': 'renew'}
            else:
                period_map = {'month': 1, '6mo': 6, 'year': 12}
                for period in period_map.keys():
                    plan['period_statuses'][period] = 'connected'

            plan['status'] = 'active'

        plans.append(plan)

    # 👇 Добавляем бесплатный тариф только для неавторизованных
    if not (user and getattr(user, 'is_authenticated', False)):
        free_plan = {
            'key': 'free',
            'title': 'Бесплатный',
            'access': False,
            'tokens': 200,
            'memory': 0.15,
            'classes': 4,
            'full_price': 0,
            'price_month': 0,
            'price_6mo': 0,
            'price_year': 0,
            'marketing_type': None,
            'end_time': None,
            'gift_tokens': 0,
            'sales': {},
            'period_statuses': {
                'month': 'connected',
                '6mo': 'connected',
                'year': 'connected',
            },
            'status': 'active'
        }
        plans.insert(0, free_plan)

    discounts_for_template = {
        'month': int(discounts.get('sub_month', 0.0) * 100),
        '6mo': int(discounts.get('sub_6mo', 0.0) * 100),
        'year': int(discounts.get('sub_year', 0.0) * 100),
    }

    return {
        'plans': plans,
        'used_gb': round(used_gb, 2),
        'tariffs_marketing_time_left': int(discounts.get('end_time')) if discounts.get('end_time') else None,
        'discounts': discounts_for_template,
        'marketing_text': discounts.get('marketing_type'),
        'is_user_authenticated': getattr(user, 'is_authenticated', False),
    }



@register.inclusion_tag('home/tokens_section.html', takes_context=True)
def render_tokens_section(context):
    request = context.get('request')
    user = getattr(request, 'user', None)

    token_packs = recount_token_prices(user)

    return {
        'token_packs': token_packs,
        'marketing_tokens_text': token_packs[0].get('marketing_type', '') if token_packs[0] else None,
        'tokens_marketing_time_left': token_packs[0].get('end_time', '') if token_packs[0] else None,
        'request': request,
    }





@register.inclusion_tag('builder/updated_templates/lesson_selection.html', takes_context=True)
def lesson_selection(context):
    """
    Возвращает контекст для шаблона выбора урока:
        - public_items: список публичных уроков (из LessonPublicData + lesson)
        - user_courses: список курсов пользователя с их уроками
    Тег берёт пользователя из context['user'] (если есть).
    """
    user = context.get('user', None)

    # Публичные данные уроков, фильтруем только по реально публичным урокам
    public_qs = LessonPublicData.objects.select_related('lesson').filter(lesson__is_public=True)
    public_items = []
    for pd in public_qs:
        l = pd.lesson
        public_items.append({
            'id': str(l.id),
            'name': l.name,
            'url_name': pd.link_name,  # в шаблоне будем urlencode
            'icon': pd.icon or '',
            'level': (pd.level or '').upper(),
            'is_public': True,  # здесь всегда True
        })

    # Курсы пользователя и их уроки
    user_courses = []
    if user and getattr(user, 'is_authenticated', False):
        courses_qs = Course.objects.filter(user=user).prefetch_related('lessons')
        for c in courses_qs:
            lessons = []
            for ls in c.lessons.all():
                lessons.append({
                    'id': str(ls.id),
                    'name': ls.name,
                    'is_public': ls.is_public,
                })
            user_courses.append({
                'id': str(c.id),
                'name': c.name,
                'lessons': lessons,
            })

    return {
        'public_items': public_items,
        'user_courses': user_courses,
        'this_step_new': False,
    }


@register.inclusion_tag("builder/updated_templates/generate_lesson.html", takes_context=True)
def generate_lesson(context):
    """Вставляет модалку для генерации урока"""
    return {}

@register.simple_tag(takes_context=True)
def show_lesson_modal(context):
    """
    Возвращает HTML модалки только если у пользователя current_step == "generation_result".
    Во всех остальных случаях — возвращает пустую строку (ничего не будет вставлено в HTML).
    """
    request = context.get("request")
    if not request or not request.user.is_authenticated:
        return ""

    onboarding = UserOnboarding.objects.filter(user=request.user).last()
    if not onboarding:
        return ""
    print(onboarding.current_step)
    if onboarding.current_step == "generation_result" or onboarding.current_step == "generation_waiting" or onboarding.current_step == "generation_feedback":
        return render_to_string("home/do_you_like_lesson_modal.html", {"user": request.user}, request=request)

    return ""