from django import template
from django.conf import settings
from django.db.models.functions import Coalesce
from django.utils import timezone
from hub.models import GenerationStats, SiteErrorLog, Classroom
import logging
from django.db.models import Q, Count, Sum, Value, DecimalField, Prefetch
from datetime import timedelta
from django.utils.html import format_html
from users.models import Payment, CustomUser, EmailTemplate, Channel, PromoCode, TariffType, UserOnboarding, UserMetrics, TelegramMetrics, Application, ArseniyApplication

register = template.Library()


@register.inclusion_tag('admin/generation_stats.html', takes_context=True)  # Добавляем takes_context=True
def generation_stats(context):
    request = context['request']  # Получаем request из контекста
    if not request or not request.user.is_staff:
        return ''

    context = {
        'stats': [],
        'error': None,
        'type_choices': GenerationStats.TYPE_CHOICES,
        'period_choices': [
            ('day', 'Последние сутки'),
            ('week', 'Последняя неделя')
        ]
    }

    try:
        # Очистка старых записей
        week_ago = timezone.now() - timedelta(weeks=1)
        GenerationStats.objects.filter(created_at__lt=week_ago).delete()

        # Получение параметров фильтрации
        period = request.GET.get('period', 'week')  # Используем request вместо template.request
        type_filter = request.GET.get('type', None)

        # Базовый запрос
        queryset = GenerationStats.objects.all()

        # Применение фильтров
        if period == 'day':
            day_ago = timezone.now() - timedelta(days=1)
            queryset = queryset.filter(created_at__gte=day_ago)
        else:
            week_ago = timezone.now() - timedelta(weeks=1)
            queryset = queryset.filter(created_at__gte=week_ago)

        if type_filter and type_filter in dict(GenerationStats.TYPE_CHOICES):
            queryset = queryset.filter(type=type_filter)

        context['stats'] = queryset.order_by('-created_at')
        context['current_period'] = period
        context['current_type'] = type_filter

    except Exception as e:
        logging.error(f"Generation stats error: {str(e)}")
        context['error'] = f"Ошибка загрузки статистики. Попробуйте позже: {str(e)}"

    return context

@register.inclusion_tag('admin/error_logs_from_users.html', takes_context=True)
def site_error_logs(context):
    request = context['request']
    if not request or not request.user.is_staff:
        return ''

    ctx = {
        'errors': [],
        'error': None,
        'period_choices': [
            ('day', 'Последние сутки'),
            ('week', 'Последняя неделя'),
        ]
    }

    try:
        period = request.GET.get('error_period', 'week')

        # Удаляем логи старше недели
        week_ago = timezone.now() - timedelta(weeks=1)
        SiteErrorLog.objects.filter(created_at__lt=week_ago).delete()

        # Базовый запрос
        queryset = SiteErrorLog.objects.all()

        if period == 'day':
            day_ago = timezone.now() - timedelta(days=1)
            queryset = queryset.filter(created_at__gte=day_ago)
        else:
            queryset = queryset.filter(created_at__gte=week_ago)

        ctx['errors'] = queryset.order_by('-created_at')
        ctx['current_period'] = period

    except Exception as e:
        logging.error(f"Site error logs load error: {str(e)}")
        ctx['error'] = f"Не удалось загрузить ошибки: {str(e)}"

    return ctx

@register.inclusion_tag('admin/payment_stats.html', takes_context=True)
def payment_stats(context):
    request = context.get('request')
    if not request or not getattr(request.user, 'is_staff', False):
        return {'payments': [], 'error': "Нет доступа"}

    show_all = request.GET.get('show_all') == '1'

    context = {
        'payments': [],
        'error': None,
        'type_choices': Payment.PaymentType.choices,
        'status_choices': Payment.Status.choices,
        'show_all': show_all,
    }

    try:
        type_filter = request.GET.get('type')
        status_filter = request.GET.get('status')
        search = request.GET.get('q', '').strip()

        queryset = Payment.objects.select_related('user').all()

        if type_filter in dict(Payment.PaymentType.choices):
            queryset = queryset.filter(payment_type=type_filter)

        if status_filter in dict(Payment.Status.choices):
            queryset = queryset.filter(status=status_filter)

        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__id__iexact=search)
            )

        queryset = queryset.order_by('-created_at')
        if not show_all:
            queryset = queryset[:15]

        context.update({
            'payments': queryset,
            'current_type': type_filter,
            'current_status': status_filter,
            'search': search,
        })

    except Exception as e:
        logging.error(f"[payment_stats] Ошибка загрузки: {str(e)}")
        context['error'] = f"Ошибка загрузки платежей. Попробуйте позже: {str(e)}"

    return context

@register.inclusion_tag('admin/user_tariffs.html', takes_context=True)
def user_tariffs(context):
    request = context.get('request')
    if not request or not getattr(request.user, 'is_staff', False):
        return {}

    search = request.GET.get('q', '').strip()
    tariff_filter = request.GET.get('tariff_type')
    status_filter = request.GET.get('tariff_status')
    role_filter = request.GET.get('role')
    show_all = request.GET.get('show_all') == '1'

    try:
        # Убираем select_related('checklist') так как этой связи больше нет
        queryset = CustomUser.objects.all().select_related('tariff').order_by('-id')

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(id__iexact=search)
            )

        if role_filter in ['teacher', 'student']:
            queryset = queryset.filter(role=role_filter)

        user_data = []
        now = timezone.now()

        # Предзагружаем данные онбординга для всех пользователей
        from users.models import UserOnboarding  # Импортируем модель онбординга
        user_ids = list(queryset.values_list('id', flat=True))

        # Получаем все записи онбординга для этих пользователей
        onboardings = UserOnboarding.objects.filter(user_id__in=user_ids)
        onboarding_by_user = {}
        for onboarding in onboardings:
            onboarding_by_user[onboarding.user_id] = onboarding

        for user in queryset:
            tariff = getattr(user, 'tariff', None)

            # Получаем информацию об онбординге из предзагруженных данных
            onboarding = onboarding_by_user.get(user.id)
            if onboarding:
                current_step = onboarding.current_step
                onboarding_status = onboarding.get_overall_status()
            else:
                current_step = '—'
                onboarding_status = False

            if tariff:
                if tariff_filter and tariff.tariff_type != tariff_filter:
                    continue
                if status_filter == 'active' and not tariff.is_active():
                    continue
                if status_filter == 'expired' and tariff.is_active():
                    continue

                period_start = tariff.start_date
                period_end = tariff.end_date
                duration = (
                    f"{period_start.strftime('%d.%m.%Y')} – {period_end.strftime('%d.%m.%Y')}"
                    if period_start and period_end else '—'
                )

                user_data.append({
                    'user': user,
                    'tariff_type': tariff.get_tariff_type_display(),
                    'tariff_type_value': tariff.tariff_type,
                    'duration': duration,
                    'period_start': period_start,
                    'period_end': period_end,
                    'status': tariff.get_status_display(),
                    'amount': '—',
                    'current_step': current_step,
                    'onboarding_status': onboarding_status,
                    'is_new': user.is_new,
                })
            else:
                if status_filter in ['active', 'expired']:
                    continue
                user_data.append({
                    'user': user,
                    'tariff_type': '—',
                    'tariff_type_value': None,
                    'duration': '—',
                    'period_start': None,
                    'period_end': None,
                    'status': 'Нет тарифа',
                    'amount': '—',
                    'current_step': current_step,
                    'onboarding_status': onboarding_status,
                    'is_new': user.is_new,
                })

        context.update({
            'users': user_data if show_all else user_data[:5],
            'total_count': len(user_data),
            'search': search,
            'tariff_filter': tariff_filter,
            'status_filter': status_filter,
            'role_filter': role_filter,
            'show_all': show_all,
        })

    except Exception as e:
        context['error'] = str(e)

    return context

@register.inclusion_tag('admin/user_metrics.html', takes_context=True)
def user_metrics(context):
    """
    Возвращает подробные параметры метрик для пользователей в контексте:
    'users' - список словарей с полями:
        - user (CustomUser instance)
        - pdf_downloaded_counter
        - ai_requests_counter
        - tasks_generated_counter
        - sections_generated_counter
        - lessons_generated_counter
        - first_activity_at
        - last_activity_at
        - retention (dict с keys 'D1','D3','D7')
        - is_new
        - onboarding_step
        - onboarding_done (bool)
    Поддерживает фильтрацию через GET-параметры:
        ?q=... (по username/email/id), ?role=teacher|student, ?teaching_role=..., ?show_all=1
    Доступ только для staff.
    """
    request = context.get('request')
    if not request or not getattr(request.user, 'is_staff', False):
        return {}

    search = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role')
    teaching_role_filter = request.GET.get('teaching_role', '').strip()
    show_all = request.GET.get('show_all') == '1'

    try:
        # Базовый queryset пользователей — отсортирован по убыванию id
        queryset = CustomUser.objects.all().select_related('tariff').order_by('-id')

        if search:
            # По username, email или точному id
            qfilter = Q(username__icontains=search) | Q(email__icontains=search)
            if search.isdigit():
                qfilter |= Q(id__iexact=search)
            queryset = queryset.filter(qfilter)

        if role_filter in ['teacher', 'student']:
            queryset = queryset.filter(role=role_filter)

        # Фильтрация по teaching_role (точное совпадение, если задано)
        if teaching_role_filter:
            queryset = queryset.filter(teaching_role=teaching_role_filter)

        # Список id пользователей в итоговом queryset
        user_ids = list(queryset.values_list('id', flat=True))

        # Предзагружаем метрики и онбординги пакетно
        metrics_qs = UserMetrics.objects.filter(user_id__in=user_ids)
        metrics_by_user = {m.user_id: m for m in metrics_qs}

        onboardings = UserOnboarding.objects.filter(user_id__in=user_ids)
        onboarding_by_user = {o.user_id: o for o in onboardings}

        user_data = []
        now = timezone.now()

        for user in queryset:
            m = metrics_by_user.get(user.id)
            onboarding = onboarding_by_user.get(user.id)

            # Заполняем значения (default если метрики нет)
            pdf_count = m.pdf_downloaded_counter if m else 0
            ai_count = m.ai_requests_counter if m else 0
            tasks_count = m.tasks_generated_counter if m else 0
            sections_count = m.sections_generated_counter if m else 0
            lessons_count = m.lessons_generated_counter if m else 0

            first_activity = m.first_activity_at if m else None
            last_activity = m.last_activity_at if m else None

            retention = {"D1": False, "D3": False, "D7": False}
            try:
                if m:
                    retention = m.retention_status()
            except Exception:
                retention = {"D1": False, "D3": False, "D7": False}

            if onboarding:
                onboarding_step = onboarding.current_step
                onboarding_done = onboarding.get_overall_status()
            else:
                onboarding_step = None
                onboarding_done = False

            # --- Новые поля: role_display и teaching_role ---
            role_display = getattr(user, 'get_role_display', lambda: getattr(user, 'role', ''))()
            teaching_role = getattr(user, 'teaching_role', '')

            user_data.append({
                'user': user,
                'id': user.id,
                'username': getattr(user, 'username', ''),
                'email': getattr(user, 'email', ''),
                'role': getattr(user, 'role', ''),
                'role_display': role_display,
                'teaching_role': teaching_role,
                'is_new': getattr(user, 'is_new', False),

                # Метрики
                'pdf_downloaded_counter': pdf_count,
                'ai_requests_counter': ai_count,
                'tasks_generated_counter': tasks_count,
                'sections_generated_counter': sections_count,
                'lessons_generated_counter': lessons_count,

                # Активность / retention
                'first_activity_at': first_activity,
                'last_activity_at': last_activity,
                'retention': retention,

                # Онбординг
                'onboarding_step': onboarding_step,
                'onboarding_done': onboarding_done,
            })

        # Ограничиваем вывод если show_all не установлен (в духе вашего примера)
        out_users = user_data if show_all else user_data[:50]  # default show up to 50

        context.update({
            'users': out_users,
            'total_count': len(user_data),
            'search': search,
            'role_filter': role_filter,
            'teaching_role_filter': teaching_role_filter,
            'show_all': show_all,
        })

    except Exception as e:
        # Возвращаем ошибку в контексте для отладки в шаблоне
        context['error'] = str(e)
        return context

    return context

@register.inclusion_tag('admin/telegram_user_metrics.html', takes_context=True)
def telegram_user_metrics(context):
    """
    Возвращает контекст для шаблона admin/telegram_user_metrics.html:
      - users: список словарей с полями:
          id, username, email, tg_id, tg_username, tg_link,
          pdf_downloaded, generation_requests, grades, levels,
          textbooks, metrics_updated_at, is_active, date_joined
      - total_count: количество пользователей
      - now: текущий timestamp
    Доступ — только staff.
    """
    request = context.get('request')
    if not request or not getattr(request.user, 'is_staff', False):
        return {}

    # Предзагружаем связанные метрики
    metrics_qs = TelegramMetrics.objects.prefetch_related(
        'grade', 'level', 'textbooks'
    ).order_by('-updated_at')  # берём последнюю запись метрик

    users_qs = CustomUser.objects.all().order_by('-id').prefetch_related(
        Prefetch('telegram_metrics', queryset=metrics_qs, to_attr='prefetched_metrics')
    )

    users_data = []
    now = timezone.now()

    for user in users_qs:
        metrics = getattr(user, 'prefetched_metrics', [])
        metrics = metrics[0] if metrics else None

        if metrics:
            tg_id = metrics.telegram_id
            tg_username = metrics.telegram_username
            pdf_downloaded = metrics.pdf_downloaded
            generation_requests = metrics.generation_requests
            grades = [g.name for g in metrics.grade.all()]
            levels = [l.name for l in metrics.level.all()]
            textbooks = [t.name for t in metrics.textbooks.all()]
            metrics_updated_at = metrics.updated_at
        else:
            tg_id = None
            tg_username = None
            pdf_downloaded = 0
            generation_requests = 0
            grades = []
            levels = []
            textbooks = []
            metrics_updated_at = None

        # Ссылка на Telegram
        tg_link = None
        if tg_id:
            tg_link = f"tg://user?id={tg_id}"
        elif tg_username:
            tg_link = f"https://t.me/{tg_username}"

        users_data.append({
            'id': user.id,
            'username': getattr(user, 'username', '') or '',
            'email': getattr(user, 'email', '') or '',
            'tg_id': tg_id,
            'tg_username': tg_username,
            'tg_link': tg_link,
            'pdf_downloaded': pdf_downloaded,
            'generation_requests': generation_requests,
            'grades': grades,
            'levels': levels,
            'textbooks': textbooks,
            'metrics_updated_at': metrics_updated_at,
            'is_active': getattr(user, 'is_active', False),
            'date_joined': getattr(user, 'date_joined', None),
        })

    return {
        'users': users_data,
        'total_count': len(users_data),
        'now': now,
        'request': request
    }

@register.inclusion_tag('admin/user_metrics_summary.html', takes_context=True)
def user_metrics_summary(context):
    """
    Возвращает сводку метрик:
      - total: количество пользователей в выборке
      - d1_count, d3_count, d7_count и их проценты (D1/D3/D7)
      - multi_gen_count: сколько пользователей сделали >1 генераций (задание+раздел+урок)
      - teachers_onboarded_done: сколько teachers с онбордингом == done
    Поддерживает GET фильтры: q (username/email/id), role, teaching_role
    Доступ только для staff.
    """
    request = context.get('request')
    if not request or not getattr(request.user, 'is_staff', False):
        return {}

    search = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role')
    teaching_role_filter = request.GET.get('teaching_role', '').strip()

    try:
        # Базовый queryset
        queryset = CustomUser.objects.all().order_by('-id')

        if search:
            qfilter = Q(username__icontains=search) | Q(email__icontains=search)
            if search.isdigit():
                qfilter |= Q(id__iexact=search)
            queryset = queryset.filter(qfilter)

        if role_filter in ['teacher', 'student']:
            queryset = queryset.filter(role=role_filter)

        if teaching_role_filter:
            queryset = queryset.filter(teaching_role=teaching_role_filter)

        # Предзагружаем метрики и онбординги пакетно
        user_ids = list(queryset.values_list('id', flat=True))
        metrics_qs = UserMetrics.objects.filter(user_id__in=user_ids)
        metrics_by_user = {m.user_id: m for m in metrics_qs}

        onboardings = UserOnboarding.objects.filter(user_id__in=user_ids)
        onboarding_by_user = {o.user_id: o for o in onboardings}

        # Счётчики
        total = len(user_ids)
        d1_count = d3_count = d7_count = 0
        multi_gen_count = 0
        teachers_onboarded_done = 0

        for user in queryset:
            m = metrics_by_user.get(user.id)
            # retention
            try:
                if m:
                    r = m.retention_status()
                    if r.get('D1'):
                        d1_count += 1
                    if r.get('D3'):
                        d3_count += 1
                    if r.get('D7'):
                        d7_count += 1
            except Exception:
                # в случае ошибки оставляем 0 для этого юзера
                pass

            # более одного запроса на генерацию (сумма трёх counters)
            if m:
                gen_sum = (
                    (m.tasks_generated_counter or 0)
                    + (m.sections_generated_counter or 0)
                    + (m.lessons_generated_counter or 0)
                )
                if gen_sum > 1:
                    multi_gen_count += 1

            # teachers, прошедшие онбординг до done
            if getattr(user, 'role', '') == 'teacher':
                ob = onboarding_by_user.get(user.id)
                if ob and ob.get_overall_status():
                    teachers_onboarded_done += 1

        # Проценты (без деления на 0)
        def percent(part, whole):
            return round((part / whole) * 100, 2) if whole else 0.0

        d1_percent = percent(d1_count, total)
        d3_percent = percent(d3_count, total)
        d7_percent = percent(d7_count, total)

        return {
            'total': total,
            'd1_count': d1_count,
            'd3_count': d3_count,
            'd7_count': d7_count,
            'd1_percent': d1_percent,
            'd3_percent': d3_percent,
            'd7_percent': d7_percent,
            'multi_gen_count': multi_gen_count,
            'teachers_onboarded_done': teachers_onboarded_done,
            # прокидываем фильтры в шаблон для отображения
            'search': search,
            'role_filter': role_filter,
            'teaching_role_filter': teaching_role_filter,
        }

    except Exception as e:
        # В случае общей ошибки возвращаем пустой контекст с информацией об ошибке
        return {'error': str(e)}

@register.inclusion_tag('admin/admin_email.html', takes_context=True)
def render_email_templates(context):
    templates = EmailTemplate.objects.all().order_by('-updated_at')
    return {'templates': templates}

@register.inclusion_tag('admin/channel_stats.html', takes_context=True)
def channel_stats(context):
    channels = Channel.objects.annotate(
        registrations=Count('customuser', distinct=True),
        purchases=Count(
            'payment',
            filter=Q(payment__status=Payment.Status.COMPLETED),
            distinct=True
        ),
        revenue=Coalesce(
            Sum(
                'payment__amount',
                filter=Q(payment__status=Payment.Status.COMPLETED)
            ),
            Value(0),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        )
    )

    return {
        'channels': channels,
        'request': context['request']
    }

@register.inclusion_tag('admin/channel_form.html', takes_context=True)
def create_channel_form(context):
    return {
        'request': context['request']
    }

@register.inclusion_tag('admin/promo_stats.html', takes_context=True)
def promo_stats(context):
    promos = PromoCode.objects.all().order_by('-created_at')
    return {
        'promos': promos,
        'promos_count': promos.count(),
        'request': context['request']
    }

@register.inclusion_tag('admin/promo_form.html', takes_context=True)
def create_promo_form(context):
    return {
        'request': context['request']
    }



@register.inclusion_tag("admin/responses_table.html")
def render_responses(limit=None):
    """
    Выводит таблицу заявок (по умолчанию все).
    Если указать limit, вернёт только последние N.
    """
    qs = Application.objects.order_by("-created_at")
    if limit:
        qs = qs[:limit]
    return {"responses": qs}

@register.inclusion_tag("admin/arseniy-application.html")
def arseniy_applications():
    apps = ArseniyApplication.objects.all().order_by("-created_at")
    return {"apps": apps}