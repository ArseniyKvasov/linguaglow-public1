from __future__ import annotations

import mimetypes
import traceback
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

import markdown

import bleach
import json
import logging
import time

import requests
from celery import states
from celery.result import AsyncResult
from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import validate_email
from django.db.models import Case, When, Value, IntegerField
import hashlib
import os
import random
import re
import secrets
import uuid
import base64

from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit

from .tasks import process_pdf_section_task, generate_audio_task, generate_task_celery, generate_lesson_task
import jwt
from PIL import Image
from datetime import timezone, date, datetime, timedelta
from html import unescape
from bs4 import BeautifulSoup
from django.conf import settings
from django.forms.models import model_to_dict
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Sum
from django.db.models import Max
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest, HttpResponseServerError, HttpResponseNotFound, FileResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.http import require_http_methods
from lzstring import LZString
from .ai_calls import generate_handler, search_images_api, has_min_tokens, add_successful_generation
from django.db.models import Case, When, IntegerField
from .forms import ClassroomForm
from django.utils import timezone
from users.models import UserTariff, TariffType, CustomUser, Notification, UserNotification, Role, UserOnboarding
from .models import Course, Section, Lesson, BaseTask, WordList, Image, MatchUpTheWords, Essay, Note, SortIntoColumns, \
    MakeASentence, Unscramble, FillInTheBlanks, Dialogue, Article, Audio, Test, TrueOrFalse, LabelImages, EmbeddedTask, \
    Classroom, UserAnswer, UserAutogenerationPreferences, Homework, LessonPublicData, MediaFile, \
    UserContextLength, Pdf, CoursePdf, SiteErrorLog, Generation, LessonGenerationStatus, PublicLessonsEmails
from users.models import TariffStatus, UserTokenBalance, UserMetrics, TelegramAuthToken

from .templatetags.custom_tags import get_user_tariff_discounts, recount_tariff_prices, recount_token_prices
from .utils import markdown_to_html, update_auto_context, enhance_query_with_params, build_base_query

User = get_user_model()
logger = logging.getLogger(__name__)

def robots_txt(request):
    content = """
    User-agent: *
    Disallow: /users/
    Disallow: /hub/dashboard/
    Disallow: /hub/profile/
    Disallow: /hub/api/
    Disallow: /static/
    Disallow: /media/
    Allow: /
    Sitemap: https://linguaglow.ru/sitemap.xml
    """
    return HttpResponse(content, content_type="text/plain")

def sitemap_view(request):
    # Текущая дата для основной страницы
    lastmod = timezone.now().date()

    # Начало XML
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="https://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://linguaglow.ru/</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://linguaglow.ru/users/registration</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://linguaglow.ru/users/login</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
"""

    # Добавляем все публичные уроки
    public_lessons = Lesson.objects.filter(is_public=True).select_related('public_data')
    for l in public_lessons:
        lesson_lastmod = l.updated_at.date()
        sitemap_xml += f"""
    <url>
        <loc>https://linguaglow.ru/public/{l.id}/</loc>
        <lastmod>{lesson_lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.7</priority>
    </url>"""

    # Закрываем XML
    sitemap_xml += "\n</urlset>"

    return HttpResponse(sitemap_xml, content_type="application/xml")

def landing(request):
    if request.user.is_authenticated:
        return redirect('home')

    return render(request, 'home/landing.html')

@login_required
def home_view(request):
    # 🚦 Проверка онбординга
    try:
        ob, _ = UserOnboarding.objects.get_or_create(user=request.user)
        if ob.current_step != "done" and getattr(request.user, 'role', '') == "teacher":
            return redirect("onboarding")
    except Exception as e:
        logger.error(f"Onboarding check error: {str(e)}")

    context = {
        'courses': [],
        'classrooms': [],
        'student_homeworks': [],
        'teacher_homeworks': [],
        'tokens': 0,
        'usage': 0,
        'usage_percent': 0,
        'max_usage': 0,
        'tariff_tooltip': "Неактивна",
        'next_reset_date': None,
        'notifications': [],
        'context_length': 2000,
        'role': getattr(request.user, 'role', ''),
        'username': getattr(request.user, 'username', ''),
        'is_tariff_active': False,
        'allow_emails': getattr(request.user, 'allow_emails', False),
        'email': getattr(request.user, 'email', ''),
        'user': request.user if request.user.is_authenticated else None,
        'is_new': False,
        'mode': 'home',
    }

    try:
        # Базовые данные пользователя
        try:
            context['tokens'] = request.user.token_balance.tokens
        except Exception as e:
            logger.error(f"Token error: {str(e)}")

        # Курсы пользователя
        try:
            context['courses'] = Course.objects.filter(user=request.user)
        except Exception as e:
            logger.error(f"Courses error: {str(e)}")

        # Классы пользователя
        try:
            context['classrooms'] = Classroom.objects.filter(
                Q(teachers=request.user) | Q(students=request.user)
            ).distinct()
        except Exception as e:
            logger.error(f"Classrooms error: {str(e)}")

        # Домашние задания студента
        try:
            student_status_order = Case(
                When(status='resent', then=Value(0)),
                When(status='sent', then=Value(1)),
                When(status='completed', then=Value(2)),
                When(status='checked', then=Value(3)),
                default=Value(4),
                output_field=IntegerField()
            )
            context['student_homeworks'] = Homework.objects.filter(
                student=request.user
            ).select_related('classroom', 'lesson').prefetch_related('tasks').annotate(
                status_order=student_status_order
            ).order_by('status_order', 'classroom__name')
        except Exception as e:
            logger.error(f"Student homeworks error: {str(e)}")

        # Домашние задания преподавателя
        try:
            if context['role'] == 'teacher':
                status_order = Case(
                    When(status='completed', then=Value(0)),
                    When(status='resent', then=Value(1)),
                    When(status='sent', then=Value(2)),
                    When(status='checked', then=Value(3)),
                    default=Value(4),
                    output_field=IntegerField()
                )
                context['teacher_homeworks'] = Homework.objects.filter(
                    classroom__teachers=request.user
                ).select_related('classroom', 'student', 'lesson').prefetch_related('tasks').annotate(
                    status_order=status_order
                ).order_by('status_order', 'classroom__name', 'student__username')
        except Exception as e:
            logger.error(f"Teacher homeworks error: {str(e)}")

        # Данные тарифа
        try:
            if context['role'] == 'teacher':
                check_user_pending_payments(request.user)
                tariff = getattr(request.user, 'tariff', None)
                if tariff:
                    context['is_tariff_active'] = tariff.is_active
                    context['tariff'] = tariff

                    if tariff.end_date is None:
                        context['tariff_tooltip'] = "Навсегда"
                    else:
                        end_date_text = tariff.end_date.strftime('%d.%m.%Y')
                        context[
                            'tariff_tooltip'] = f"Активен до {end_date_text}" if tariff.end_date.date() >= date.today() else "Неактивна"

                    context['next_reset_date'] = tariff.get_next_reset_date_display()

                    cfg = settings.TARIFFS.get(tariff.tariff_type, {})
                    gb = cfg.get('memory_gb', 0)
                    context['max_usage'] = gb
                    try:
                        context['usage'] = round(request.user.used_storage / 1024 ** 3, 2)
                        context['usage_percent'] = int((context['usage'] / gb) * 100) if gb else 0
                    except ZeroDivisionError:
                        context['usage_percent'] = 0
        except Exception as e:
            logger.error(f"Tariff error: {str(e)}")

        # Уведомления
        try:
            notifications = Notification.objects.filter(
                is_active=True,
                target_roles__contains=[context['role']]
            )
            hidden_ids = UserNotification.objects.filter(
                user=request.user,
                is_hidden=True
            ).values_list('notification_id', flat=True)
            context['notifications'] = notifications.exclude(id__in=hidden_ids)
        except Exception as e:
            logger.error(f"Notifications error: {str(e)}")

        # Длина контекста
        try:
            context['context_length'] = request.user.context_length.context_length
        except Exception as e:
            logger.error(f"Context length error: {str(e)}")

        try:
            metrics, _ = UserMetrics.objects.get_or_create(user=request.user)
            metrics.update_activity()
            context['retention'] = metrics.retention_status()
        except Exception as e:
            logger.error(f"User metrics error: {str(e)}")
            context['retention'] = {"D1": False, "D3": False, "D7": False}

        try:
            context['is_new'] = request.user.is_new
        except AttributeError as e:
            logger.error(f"Ошибка получения флага is_new: {str(e)}")
            context['is_new'] = False  # Устанавливаем значение по умолчанию при ошибке
        except Exception as e:
            logger.error(f"Неизвестная ошибка при получении is_new: {str(e)}")
            context['is_new'] = False  # Устанавливаем значение по умолчанию при любой другой ошибке

    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")
        if request.user.is_authenticated:
            add_successful_generation("functions", False,
                                      f"{str(e)} USER: {request.user.username} ID: {request.user.id}")

    return render(request, 'home/home.html', context)

@login_required
@require_POST
def save_context_length(request):
    try:
        data = json.loads(request.body)
        value = int(data.get('context_length'))
    except (json.JSONDecodeError, TypeError, ValueError):
        return HttpResponseBadRequest("Некорректные данные")

    # Создаём или обновляем запись
    obj, _ = UserContextLength.objects.update_or_create(
        user=request.user,
        defaults={'context_length': value}
    )
    return JsonResponse({'status': 'ok', 'context_length': obj.context_length})

@login_required
@require_POST
def update_subscription(request):
    try:
        # Получаем значение подписки из запроса
        subscribe = request.POST.get('subscribe', False)

        # Обновляем статус подписки пользователя
        user = request.user
        user.allow_emails = subscribe in ['true', 'True', '1', True]
        user.save()

        return JsonResponse({
            'success': True,
            'message': 'Настройки подписки успешно обновлены'
        }, status=200)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

def shop_view(request):
    return render(request, 'home/shop.html')

@ratelimit(key='ip', rate='10/h', block=True)
def create_course(request):
    print("➡️ create_course called, method:", request.method)

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        student_level = request.POST.get('student_level')
        print(f"📥 POST data: name={name}, description={description}, student_level={student_level}")

        # проверяем роль
        user_role = getattr(request.user, "role", None)
        print(f"👤 user={request.user} role={user_role} is_staff={request.user.is_staff}")

        if user_role != "teacher":
            print("❌ Access denied: not a teacher")
            return JsonResponse({'error': 'You are not a teacher'}, status=403)

        try:
            with transaction.atomic():
                print("🔨 Creating course...")
                new_course = Course.objects.create(
                    name=name,
                    description=description,
                    student_level=student_level,
                    user=request.user
                )
                print(f"✅ Course created: {new_course} (id={new_course.id})")

                print("⚙️ Creating default autogeneration prefs...")
                create_default_autogeneration_prefs(new_course)
                print("✅ Prefs created")

                print("📚 Creating Lesson 1...")
                first_lesson = Lesson.objects.create(
                    course=new_course,
                    name="Lesson 1",
                    is_public=False,
                    context={}
                )
                print(f"✅ Lesson created: {first_lesson} (id={first_lesson.id})")

                print("📂 Creating Section...")
                section = Section.objects.create(
                    lesson=first_lesson,
                    name="Let's begin! 😉",
                    type='learning'
                )
                print(f"✅ Section created: {section} (id={section.id})")

            print("🔀 Redirecting to lesson_list...")
            return redirect('lesson_list', course_id=new_course.id)

        except Exception as e:
            import traceback
            print("💥 Exception occurred in create_course!")
            print(traceback.format_exc())
            return JsonResponse({'error': str(e)}, status=500)

    print("↩️ Not POST, redirecting to home")
    return redirect('home')

def create_default_autogeneration_prefs(course):
    """
    Создаёт дефолтные UserAutogenerationPreferences для курса.
    Можно переиспользовать и при создании курса, и при восстановлении.
    """
    return UserAutogenerationPreferences.objects.create(
        course=course,
        task_types_lexical=[
            {"WordList": {"user_query": "Составьте список из 15 распространенных слов или фраз с переводами на русский язык."}},
            {"MatchUpTheWords": {"user_query": "Создайте 10 пар слов и их переводов для упражнения на сопоставление."}},
            {"Unscramble": {"user_query": "Выберите 5 ключевых слов и дайте русскоязычные подсказки для их угадывания."}},
            {"MakeASentence": {"user_query": "Напишите 5 коротких предложений (по 5-7 слов каждое)."}},
            {"LabelImages": {"user_query": "Подберите 6 слов, подходящих для подписи изображений."}},
            {"FillInTheBlanks": {
                "user_query": "Напишите предложения с 7 пропусками для заполнения подходящими словами."}},
        ],
        task_types_listening=[
            {"Audio": {
                "user_query": "Придумайте название и напишите монолог-сценарий подкаста (150 слов) по теме урока."}},
            {"TrueOrFalse": {
                "user_query": "Создайте 5 сложных утверждений типа 'верно/неверно' для аудирования."}},
        ],
        task_types_reading=[
            {"Article": {"user_query": "Придумайте название и напишите текст для чтения (200+ слов) по теме урока."}},
            {"Test": {"user_query": "Составьте 5 вопросов на понимание прочитанного."}},
        ],
        task_types_grammar=[
            {"Note": {
                "user_query": "Кратко объясните использование и цель грамматической темы (на русском с английскими примерами)."}},
            {"TrueOrFalse": {
                "user_query": "Создайте 4 утверждения 'верно/неверно' на русском для проверки понимания материала."}},
            {"Test": {"user_query": "Создайте 10 четких грамматических вопросов по теме урока."}},
            {"FillInTheBlanks": {
                "user_query": "Напишите 6 предложений с одним пропуском в каждом; укажите базовую форму глагола в скобках при необходимости."}},
        ],
        task_types_speaking=[
            {"Note": {
                "user_query": "Создайте 10 вопросов-подсказок для диалога по теме урока."}},
            {"Note": {"user_query": "Создайте 3 открытых вопроса для монолога по теме урока."}},
        ],
        task_types_other=[
            {"WordList": {"user_query": "Составьте список из 10 ключевых слов или фраз из урока."}},
            {"MatchUpTheWords": {"user_query": "Создайте 7 пар слов и переводов для повторения."}},
            {"FillInTheBlanks": {"user_query": "Напишите 6 предложений с пропусками для повторения лексики."}},
            {"Note": {"user_query": "Кратко суммируйте основную грамматическую тему с примерами."}},
            {"Test": {"user_query": "Создайте 6 четких грамматических вопросов по теме урока."}},
            {"Note": {"user_query": "Подведите итоги урока, используя эмодзи."}},
        ],
    )

def delete_course(request, course_id):
    course_to_delete = get_object_or_404(Course, id=course_id)

    if request.method == "POST" and course_to_delete.user == request.user:
        with transaction.atomic():
            # Удаляем все задания через delete_task_handler
            for lesson in course_to_delete.lessons.all():
                for section in lesson.sections.all():
                    tasks = BaseTask.objects.filter(section=section)
                    for task in tasks:
                        delete_task_handler(request.user, task)
                    section.delete()  # удаляем секцию после заданий
                lesson.delete()  # удаляем урок после секций

            # Удаляем сам курс
            course_to_delete.delete()

    return redirect('home')

def lesson_list_view(request, course_id):
    try:
        selected_course = get_object_or_404(Course, id=course_id)
        if not (request.user == selected_course.user):
            return HttpResponseForbidden("You do not have access to this lesson.")

        lessons = Lesson.objects.filter(course=selected_course)
        pdfs = CoursePdf.objects.filter(course=selected_course).order_by('-uploaded_at')

        # Передаём уроки и пользователя в контекст для рендера
        return render(request, 'home/lesson_list.html', {
        'lessons': lessons,
        'user': request.user,
        'pdfs': pdfs,
        'course': selected_course,
        'is_staff': request.user.is_staff,
    })
    except Exception as e:
        print(e)

@ratelimit(key='ip', rate='10/m', block=True)
def update_lesson_name(request, lesson_id):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        if name:
            lesson_obj = Lesson.objects.get(id=lesson_id)

            if lesson_obj.course.user != request.user:
                return HttpResponseForbidden("You do not have access to this lesson.")

            lesson_obj.name = name
            lesson_obj.save()
            return JsonResponse({"name": lesson_obj.name})
    return JsonResponse({"error": "Invalid request"}, status=400)

def clone_content_object(obj):
    """
    Создаёт клон объекта content_object с новым ID.
    """
    obj.pk = None  # сбрасываем ID
    obj.save()
    return obj

def clone_section(old_section, new_section, user):
    """
    Клонирует все задачи и медиа из old_section в new_section.
    user — текущий пользователь, чтобы обновлять использованное хранилище.
    """
    # Получаем все задачи старой секции
    old_tasks = BaseTask.objects.filter(section=old_section).prefetch_related('media', 'content_type')

    for t in old_tasks:
        original_content = t.content_object
        if not original_content:
            continue

        # Клонируем объект контента
        cloned_content = clone_content_object(original_content)
        content_type = ContentType.objects.get_for_model(cloned_content)

        # Создаем новую задачу
        new_task = BaseTask.objects.create(
            section=new_section,
            order=t.order,
            content_type=content_type,
            object_id=cloned_content.id,
            size=t.size
        )

        # Обновляем использованное место у пользователя
        user.update_used_storage(t.size)

def add_lesson(request, course_id):
    try:
        selected_course = get_object_or_404(Course, id=course_id)

        if request.method == 'POST':
            name = request.POST.get('name')

            # Проверка роли
            is_admin = request.user.is_staff

            # Получение данных с проверкой прав
            public_data = {}
            try:
                if is_admin:
                    public_data = {
                        'lexical_topics': request.POST.get('lexical_topics'),
                        'grammar_topics': request.POST.get('grammar_topics'),
                        'extra_topics': request.POST.get('extra_topics'),
                        'meta_description': request.POST.get('meta_description'),
                        'keywords': request.POST.get('keywords'),
                        'icon': request.POST.get('icon'),
                        'level': request.POST.get('level', 'A1'),
                        'is_public': 'is_public' in request.POST
                    }
                else:
                    public_data = {
                        'is_public': False
                    }

                # Контекст от предыдущего урока
                previous_lesson = selected_course.lessons.order_by('-created_at').first()
                context = previous_lesson.context if previous_lesson else {}

                with transaction.atomic():
                    # Создание урока
                    lesson_obj = Lesson.objects.create(
                        course=selected_course,
                        name=name,
                        is_public=public_data['is_public'],
                        context=context
                    )

                    # Создание публичных данных, если админ
                    if is_admin:
                        LessonPublicData.objects.create(
                            lesson=lesson_obj,
                            lexical_topics=public_data.get('lexical_topics'),
                            grammar_topics=public_data.get('grammar_topics'),
                            extra_topics=public_data.get('extra_topics'),
                            meta_description=public_data.get('meta_description'),
                            keywords=public_data.get('keywords'),
                            icon=public_data.get('icon'),
                            level=public_data.get('level', 'A1'),
                        )

                    # Создание стартовой секции
                    Section.objects.create(
                        lesson=lesson_obj,
                        name="Let's begin! 😉",
                        type='learning'
                    )

                    # Дублирование revision-секций
                    if previous_lesson:
                        rev_sections = previous_lesson.sections.filter(type='revision')

                        for rev in rev_sections:
                            new_sec = Section.objects.create(
                                lesson=lesson_obj,
                                name=rev.name,
                                type='completion'
                            )
                            clone_section(rev, new_sec, request.user)

                return redirect('lesson_list', course_id=course_id)

            except ValidationError as ve:
                logger.error(f"Validation error: {ve}")
                raise
            except Exception as e:
                logger.error(f"Error during lesson creation: {e}")
                raise

    except Exception as e:
        logger.critical(f"Critical error in add_lesson: {e}")
        return redirect('lesson_list', course_id=course_id)

    return redirect('lesson_list', course_id=course_id)

def update_lesson(request, lesson_id):
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id)

        if request.method == 'POST':
            # Проверяем, есть ли файлы
            if request.FILES:
                pdf_file = request.FILES.get('pdf_file')
            else:
                pdf_file = None

            # Получаем остальные данные из POST
            name = request.POST.get('name')
            is_admin = request.user.is_staff

            public_data = {}
            if is_admin:
                public_data = {
                    'lexical_topics': request.POST.get('lexical_topics'),
                    'grammar_topics': request.POST.get('grammar_topics'),
                    'extra_topics': request.POST.get('extra_topics'),
                    'meta_description': request.POST.get('meta_description'),
                    'keywords': request.POST.get('keywords'),
                    'icon': request.POST.get('icon'),
                    'level': request.POST.get('level', 'A1'),
                    'is_public': 'is_public' in request.POST
                }
            else:
                public_data = {
                    'is_public': False
                }

            with transaction.atomic():
                # Обновляем основной урок
                lesson.name = name
                lesson.is_public = public_data['is_public']
                lesson.save()

                # Обновляем публичные данные
                public_data_obj = lesson.public_data
                public_data_obj.lexical_topics = public_data.get('lexical_topics')
                public_data_obj.grammar_topics = public_data.get('grammar_topics')
                public_data_obj.extra_topics = public_data.get('extra_topics')
                public_data_obj.meta_description = public_data.get('meta_description')
                public_data_obj.keywords = public_data.get('keywords')
                public_data_obj.icon = public_data.get('icon')
                public_data_obj.level = public_data.get('level', 'A1')

                # Обрабатываем загрузку файла
                if pdf_file:
                    public_data_obj.pdf_file = pdf_file
                else:
                    public_data_obj.pdf_file = None

                public_data_obj.save()

            return JsonResponse({'success': True})

    except ValidationError as ve:
        print("Validation error:", ve)
        logger.error(f"Validation error: {ve}")
        return JsonResponse({'success': False, 'error': str(ve)}, status=400)
    except Exception as e:
        print("[EXCEPTION]: ", e)
        logger.error(f"Error during lesson update: {e}")
        return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@require_POST
def get_course_pdfs(request):
    course_id = request.POST.get('course_id')
    if not course_id:
        return JsonResponse({'error': 'Не передан course_id'}, status=400)

    try:
        course_obj = Course.objects.get(id=course_id, user=request.user)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Курс не найден или нет прав'}, status=403)

    if not request.user == course_obj.user:
        return JsonResponse({'error': 'Недостаточно прав'}, status=403)

    pdfs = CoursePdf.objects.filter(course=course_obj).order_by('-uploaded_at')

    pdf_list = [{
        'id': pdf.id,
        'title': pdf.title,
        'url': pdf.url,
        'uploaded_at': pdf.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
    } for pdf in pdfs]

    return JsonResponse({'pdfs': pdf_list})

def lesson_page_view(request, lesson_id):
    try:
        # Получение урока и курса с проверкой существования
        lesson_obj = get_object_or_404(Lesson, id=lesson_id)
        course_obj = get_object_or_404(Course, id=lesson_obj.course.id)

        # Проверка прав доступа
        if request.user != course_obj.user:
            return HttpResponseForbidden("You do not have access to this lesson.")

        # Получение и сортировка секций
        sections = get_sorted_sections(lesson_obj)
        section_ids = [section.id for section in sections]

        # Создание порядка сортировки секций
        section_ordering = Case(
            *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
            output_field=IntegerField()
        )

        # Получение задач с сортировкой
        tasks = (
            BaseTask.objects.filter(section__in=section_ids)
            .select_related('content_type')
            .annotate(section_order=section_ordering)
            .order_by('section_order', 'order')
        )

        # Получение классов пользователя
        classrooms = Classroom.objects.filter(
            Q(teachers=request.user) | Q(students=request.user)
        ).distinct()

        # Работа с флагами пользователя
        try:
            # Обработка флага нового поколения
            is_new = request.user.is_new
        except Exception as e:
            logger.error(f"Ошибка при работе с флагами пользователя: {str(e)}")
            is_new = False

        # Формирование контекста для рендера
        return render(request, 'builder/updated_templates/generation.html', {
            'course_id': course_obj.id,
            'lesson': lesson_obj,
            'section_list': sections,
            'tasks': tasks,
            'classrooms': classrooms,
            'user_role': 'teacher',
            'user_id': request.user.id,
            'mode': 'generation',
            'tokens': getattr(request.user.token_balance, 'tokens', 0),
            'is_new': is_new,
        })

    except Exception as e:
        logger.exception("Ошибка в lesson_page_view (lesson_id=%s)", lesson_id)
        return HttpResponseServerError("Произошла внутренняя ошибка сервера")

@require_POST
def reorder_sections(request, lesson_id):
    try:
        data = json.loads(request.body)
        section_ids = data.get("order", [])  # список id в новом порядке

        first_section = Section.objects.get(id=section_ids[0])
        if request.user != first_section.lesson.course.user:
            return JsonResponse(
                {"status": "error", "message": "Нет прав для изменения порядка секций"},
                status=403
            )

        for index, section_id in enumerate(section_ids):
            Section.objects.filter(id=section_id, lesson_id=lesson_id).update(order=index)

        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

def delete_lesson(request, lesson_id):
    lesson_to_delete = get_object_or_404(Lesson, id=lesson_id)

    if request.user != lesson_to_delete.course.user:
        return HttpResponseForbidden("You do not have access to this lesson.")

    for section in lesson_to_delete.sections.all():
        tasks = BaseTask.objects.filter(section=section)
        for task in tasks:
            delete_task_handler(request.user, task)
        section.delete()

    course_id = lesson_to_delete.course.id

    if request.method == "POST":
        lesson_to_delete.delete()

    return HttpResponseRedirect(reverse('lesson_list', args=[course_id]))

def add_section(request, lesson_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            section_name = data.get('name')
            section_type = data.get('type', 'learning')  # по умолчанию 'learning'

            if not section_name:
                return JsonResponse({'error': 'Название раздела не может быть пустым'}, status=400)

            lesson_obj = get_object_or_404(Lesson, id=lesson_id)

            if lesson_obj.course.user != request.user:
                return JsonResponse({'error': 'Вы не можете добавлять разделы в урок, который не принадлежит вам.'}, status=403)

            # Создаём раздел, учитывая тип
            section_obj = Section.objects.create(
                lesson=lesson_obj,
                name=section_name,
                type=section_type  # если поле type есть в модели
            )
            return JsonResponse({
                'success': True,
                'section_id': section_obj.id,
                'name': section_obj.name,
                'type': section_obj.type
            })
        except Exception as e:
            print(e)
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

def update_section(request, section_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_name = data.get('name')
            new_type = data.get('type')

            # Валидация имени
            if not new_name:
                return JsonResponse(
                    {'error': 'Название раздела не может быть пустым.'},
                    status=400
                )

            # Валидация типа
            valid_types = ['learning', 'hometask', 'revision']
            if new_type and new_type not in valid_types:
                return JsonResponse(
                    {'error': f"Неверный тип раздела: {new_type}."},
                    status=400
                )

            section_obj = get_object_or_404(Section, id=section_id)

            # Проверка прав пользователя
            if section_obj.lesson.course.user != request.user:
                return JsonResponse(
                    {'error': 'Вы не можете редактировать разделы урока, который не принадлежит вам.'},
                    status=403
                )

            # Применяем изменения
            section_obj.name = new_name
            if new_type:
                section_obj.type = new_type
            section_obj.save()

            return JsonResponse({
                'success': True,
                'new_name': new_name,
                'new_type': section_obj.type
            })

        except json.JSONDecodeError:
            return JsonResponse(
                {'error': 'Неверный формат JSON.'},
                status=400
            )
        except Exception as e:
            return JsonResponse(
                {'error': str(e)},
                status=500
            )

    return JsonResponse(
        {'error': 'Метод не поддерживается.'},
        status=405
    )

def delete_section_view(request, section_id):
    section_obj = get_object_or_404(Section, id=section_id)

    if request.user != section_obj.lesson.course.user:
        return JsonResponse({'error': 'Вы не можете удалять разделы этого урока.'}, status=403)

    if len(section_obj.lesson.sections.all()) == 1:
        return JsonResponse({'error': 'Нельзя удалить последний раздел.'}, status=400)

    if request.method == "POST":
        with transaction.atomic():
            tasks = BaseTask.objects.filter(section=section_obj)
            for task in tasks:
                delete_task_handler(request.user, task)

            section_obj.delete()

        return JsonResponse({'success': True, 'section_id': section_id})

    return JsonResponse({'error': 'Неверный метод запроса'}, status=405)

TYPE_ORDER = [
    ("completion", "Закрепление"),
    ("learning",   "Обучающий"),
    ("hometask",   "Домашнее задание"),
    ("revision",   "Повторение"),
]

def get_sorted_sections(lesson_obj):
    grouped = {type_name: [] for type_name, _ in TYPE_ORDER}

    # сгруппировали секции по типам
    for s in lesson_obj.sections.all():
        grouped[s.type].append(s)

    ordered_sections = []
    for type_name, _ in TYPE_ORDER:
        if grouped[type_name]:
            # сортируем внутри группы по order
            grouped[type_name].sort(key=lambda s: s.order)

            # переназначаем порядок, если есть дубликаты или пропуски
            for idx, section in enumerate(grouped[type_name], start=1):
                if section.order != idx:  # обновляем только если отличается
                    section.order = idx
                    section.save(update_fields=["order"])

            ordered_sections.extend(grouped[type_name])

    return ordered_sections

def download_pdf_page_view(request, lesson_id):
    try:
        # Получение урока и курса
        lesson_obj = get_object_or_404(Lesson, id=lesson_id)
        course_obj = lesson_obj.course

        # Проверка прав доступа
        if request.user != course_obj.user and not lesson_obj.is_public:
            return HttpResponseForbidden("You do not have access to this lesson.")

        # Получение и сортировка секций
        sections = get_sorted_sections(lesson_obj)
        section_ids = [section.id for section in sections]

        # Создание порядка сортировки секций
        section_ordering = Case(
            *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
            output_field=IntegerField()
        )

        # Получение задач с сортировкой
        tasks = (
            BaseTask.objects.filter(section__in=section_ids)
            .select_related("content_type")
            .annotate(section_order=section_ordering)
            .order_by("section_order", "order")
        )

        # Обработка онбординга
        show_modal = False
        try:
            onboarding = UserOnboarding.objects.select_related('user').get(user=request.user)
            if onboarding.current_step == "generation_feedback":
                show_modal = True
                # Обновляем статус
                onboarding.current_step = "done"
                give_present(request)
                onboarding.save(update_fields=["current_step"])
        except UserOnboarding.DoesNotExist:
            pass

        return render(
            request,
            "builder/updated_templates/pdf_select.html",
            {
                "lesson": lesson_obj,
                "tasks": tasks,
                "showModalOnLoad": show_modal,
                "is_new": request.user.is_new,
            }
        )

    except Exception as e:
        logger.exception("Ошибка при загрузке PDF страницы: %s", str(e))
        return HttpResponseServerError("Произошла ошибка при обработке запроса")

def audio_qr_page(request, audio_url):
    # Путь до файла на сервере
    file_path = os.path.join(settings.MEDIA_ROOT, 'uploads', audio_url)

    # Проверка существования файла
    if not os.path.isfile(file_path):
        raise Http404("Аудиофайл не найден")

    # Полный URL для вставки в <audio>
    audio_full_url = f"{request.scheme}://{request.get_host()}/media/uploads/{audio_url}"

    # Рендерим HTML с плеером
    return render(request, 'builder/updated_templates/audio_player.html', {
        'audio_url': audio_full_url,
    })

ALLOWED_IFRAME_SOURCES = [
    # Wordwall (основной и staging, с поддержкой языковых кодов)
    re.compile(r'^https://(?:www\.)?(?:wordwall\.net|wordwall-live-staging\.azurewebsites\.net)(?:/[a-z]{2})?/embed(?:/|$|\?)'),

    # Miro
    re.compile(r'^https://(?:www\.)?miro\.com/app/(?:live-)?embed(?:/|$|\?)'),

    # Quizlet (любой тип встраиваемого модуля)
    re.compile(r'^https://(?:www\.)?quizlet\.com/\d+/[^/]+/embed(?:/|$|\?)'),

    # LearningApps
    re.compile(r'^https://learningapps\.org/(?:embed|watch)(?:/|$|\?).*'),

    # Rutube
    re.compile(r'^https://rutube\.ru/.*/embed(?:/|$|\?)'),

    # YouTube (обычный и nocookie)
    re.compile(r'^https://(?:www\.)?youtube(?:-nocookie)?\.com/embed(?:/|$|\?)'),

    # sBoard
    re.compile(r'^https://sboard\.online/boards/[a-f0-9\-]+$'),
]

def is_iframe_code_safe(iframe_code: str) -> bool:
    match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', iframe_code)
    if not match:
        return False
    src = match.group(1)
    return any(pattern.search(src) for pattern in ALLOWED_IFRAME_SOURCES)

def iframe_qr_page(request, compressed_code):
    if not compressed_code:
        raise Http404("Встроенный контент не найден")

    # 1. Декодируем LZ-String
    try:
        lz = LZString()
        src = lz.decompressFromEncodedURIComponent(compressed_code)
        if not src:
            raise ValueError("не удалось декомпрессировать")
    except Exception as e:
        raise Http404(f"Невозможно декомпрессировать iframe: {e}")

    # 2. Собираем минимальный тег <iframe>
    decoded_iframe = f'<iframe src="{src}"></iframe>'

    # 3. Безопасность
    if not is_iframe_code_safe(decoded_iframe):
        raise Http404("Встроенный контент заблокирован по соображениям безопасности")

    # 4. Рендерим страницу
    return render(request, 'builder/updated_templates/iframe.html', {
        'iframe_code': decoded_iframe,
    })





def getContext(request, lesson_id):
    lesson_obj = get_object_or_404(Lesson, id=lesson_id)

    if request.method == "GET":
        return JsonResponse({'context': lesson_obj.context or ""})

def addContextElement(request, lesson_id):
    if request.method != "POST":
        return JsonResponse({"error": "Доступ запрещен."}, status=405)

    # Получаем урок
    lesson_instance = get_object_or_404(Lesson, id=lesson_id)

    # Проверяем, является ли пользователь создателем курса
    if request.user != lesson_instance.course.user:
        return JsonResponse({"error": "Доступ запрещен."}, status=403)

    # Получаем данные из тела запроса
    try:
        data = json.loads(request.body)
        task_id = data.get("task_id")
        header = data.get("header", "Заметка")
        content = data.get("content", "Контент")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Данные переданы неверно."}, status=400)

    if not content:
        return JsonResponse({"error": "Текст не найден."}, status=400)

    # Загружаем существующий контекст
    context = lesson_instance.context or {}

    # Если task_id отсутствует, используем текстовый ключ
    if not task_id:
        task_id = f"text_{uuid.uuid4().hex[:8]}"

    # Проверяем, существует ли уже такой task_id
    if task_id in context:
        return JsonResponse({"error": "Вы уже добавили это задание в контекст."}, status=400)


    # Добавляем новый элемент
    context[task_id] = {"header": header, "content": content}
    lesson_instance.context = context
    lesson_instance.save()

    return JsonResponse({"message": "Задание успешно добавлено", "task_id": task_id, "header": header, "content": content}, status=201)

def removeTaskFromContext(request, lesson_id, task_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Доступ запрещен."}, status=405)

    # Получаем урок
    lesson_instance = get_object_or_404(Lesson, id=lesson_id)

    # Проверяем, имеет ли пользователь доступ
    if request.user != lesson_instance.course.user:
        return JsonResponse({"error": "Доступ запрещен."}, status=403)

    # Получаем текущий контекст урока
    context = lesson_instance.context or {}

    # Проверяем, есть ли такой task_id
    if task_id not in context:
        return JsonResponse({"error": "Такого задания в контексте нет."}, status=404)

    # Удаляем задание
    del context[task_id]
    lesson_instance.context = context
    lesson_instance.save()

    return JsonResponse({"message": "Задание успешно удалено.", "task_id": task_id}, status=200)





        # Получение заданий





def get_section_tasks(request, section_id):
    try:
        section_instance = get_object_or_404(Section, id=section_id)
        tasks = BaseTask.objects.filter(section=section_instance)
        data = {}
        for task in tasks:
            data[task.content_type.model] = task.id
        return JsonResponse(data)
    except Exception as e:
        print(e)
        return JsonResponse({"error": str(e)}, status=500)

@ratelimit(key='ip', rate='800/m', block=True)
def get_task_data(request, task_id):
    try:
        task_instance = get_object_or_404(BaseTask, id=task_id)
        content_type = task_instance.content_type
        content_object = task_instance.content_object
        model_cls = content_type.model_class()

        data = {"id": task_id, "taskType": content_type.model}

        # --- Прямые типы ---
        if model_cls == WordList:
            data.update({
                "title": clear_text(content_object.title),
                "words": content_object.words,
            })

        elif model_cls == MatchUpTheWords:
            data.update({
                "title": clear_text(content_object.title),
                "pairs": content_object.pairs,
            })

        elif model_cls == Essay:
            data.update({
                "title": clear_text(content_object.title),
                "conditions": content_object.conditions,
            })

        elif model_cls == Note:
            data.update({
                "title": clear_text(content_object.title),
                "content": clear_text(content_object.content),
            })

        elif model_cls == Image:
            data.update({
                "title": clear_text(content_object.title),
                "image_url": content_object.image_url,
            })

        elif model_cls == Dialogue:
            data.update({
                "title": clear_text(content_object.title),
                "lines": content_object.lines,
            })

        elif model_cls == Article:
            data.update({
                "title": clear_text(content_object.title),
                "content": clear_text(content_object.content),
            })

        elif model_cls == EmbeddedTask:
            embed_code = content_object.embed_code if is_iframe_code_safe(content_object.embed_code) else ""
            data.update({
                "title": clear_text(content_object.title),
                "embed_code": embed_code,
            })

        elif model_cls == Pdf:
            data.update({
                "title": clear_text(content_object.title),
                "pdf_url": content_object.pdf_url,
            })

        # --- Типы с разграничением по user ---
        elif model_cls in [SortIntoColumns, MakeASentence, Unscramble, FillInTheBlanks,
                           Test, TrueOrFalse, LabelImages, Audio]:

            is_owner = (request.user == task_instance.section.lesson.course.user)

            if model_cls == SortIntoColumns:
                columns = content_object.columns
                labels = []

                if not is_owner:
                    # скрыть слова
                    for column in columns:
                        for i, word in enumerate(column['words']):
                            column['words'][i] = '/'
                            labels.append(word)
                else:
                    for column in columns:
                        labels.extend(column['words'])

                random.shuffle(labels)
                data.update({
                    "title": clear_text(content_object.title),
                    "columns": columns,
                    "labels": labels,
                })

            elif model_cls == MakeASentence:
                sentences = content_object.sentences

                if not is_owner:
                    for s in sentences:
                        s['correct'] = '/ ' * (len(s['correct'].split()) - 1)

                data.update({
                    "title": clear_text(content_object.title),
                    "sentences": sentences,
                })

            elif model_cls == Unscramble:
                words = content_object.words

                if not is_owner:
                    for w in words:
                        w['word'] = '/' * len(w['word'])

                data.update({
                    "title": clear_text(content_object.title),
                    "words": words,
                })

            elif model_cls == FillInTheBlanks:
                text = content_object.text
                labels = re.findall(r'\[(.*?)\]', text)

                if not is_owner:
                    text = re.sub(r'\[(.*?)\]', lambda m: '[/]', text)
                    if content_object.display_format != "withList":
                        labels = []
                    else:
                        random.shuffle(labels)
                else:
                    random.shuffle(labels)

                data.update({
                    "title": clear_text(content_object.title),
                    "text": clear_text(text),
                    "display_format": content_object.display_format,
                    "labels": labels,
                })

            elif model_cls == Test:
                questions = content_object.questions
                if not is_owner:
                    for q in questions:
                        for ans in q["answers"]:
                            ans["is_correct"] = False

                data.update({
                    "title": clear_text(content_object.title),
                    "questions": questions,
                })

            elif model_cls == TrueOrFalse:
                statements = content_object.statements
                if not is_owner:
                    for s in statements:
                        s["is_true"] = False

                data.update({
                    "title": clear_text(content_object.title),
                    "statements": statements,
                })

            elif model_cls == LabelImages:
                images = content_object.images
                labels = [img['label'] for img in images]

                if not is_owner:
                    for img in images:
                        img['label'] = '/'

                random.shuffle(labels)
                data.update({
                    "title": clear_text(content_object.title),
                    "images": images,
                    "labels": labels,
                })

            elif model_cls == Audio:
                transcript = content_object.transcript if is_owner else ""
                data.update({
                    "title": clear_text(content_object.title),
                    "audio_url": content_object.audio_url,
                    "transcript": clear_text(transcript),
                })

        else:
            return JsonResponse({"error": "Unknown task type"}, status=400)

        return JsonResponse(data)

    except Exception as e:
        print(e)
        return JsonResponse({"error": str(e)}, status=500)

def clear_text(text: str) -> str:
    """
    Чистит HTML от XSS с помощью bleach и конвертирует результат в Markdown.
    Разрешает базовые теги, классы и стили.
    Полностью запрещает ссылки <a>.
    """
    allowed_tags = [
        "b", "i", "u", "em", "strong", "p", "br",
        "ul", "ol", "li", "span", "div",
        "h1", "h2", "h3", "h4", "h5", "h6"
    ]

    allowed_attributes = {
        "*": ["class", "style"],  # оставляем классы и inline-стили
    }

    # очищаем HTML
    cleaned_html = bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=[],   # запрет любых ссылочных протоколов
        strip=True
    )

    return cleaned_html

def normalize_payloads(payloads):
    if isinstance(payloads, dict):
        return payloads
    return model_to_dict(payloads)

def extract_media_ids(task_type, payloads):
    media_ids = []

    def find_media_by_url(url):
        if url and "/media/" in url:
            relative_path = url.split("/media/")[-1]
            try:
                media = MediaFile.objects.get(file=relative_path)
                return str(media.id)
            except MediaFile.DoesNotExist:
                print(f"[WARN] MediaFile не найден по пути: {relative_path}")
        return None

    payloads = normalize_payloads(payloads)

    if task_type == 'Image':
        url = payloads.get('image_url')
        media_id = find_media_by_url(url)
        if media_id:
            media_ids.append(media_id)

    elif task_type == 'Audio':
        url = payloads.get('audio_url')
        media_id = find_media_by_url(url)
        if media_id:
            media_ids.append(media_id)

    elif task_type == 'LabelImages':
        for item in payloads.get('images', []):
            url = item.get('media_url') or item.get('url')
            media_id = find_media_by_url(url)
            if media_id:
                media_ids.append(media_id)

    elif task_type == 'Pdf':
        url = payloads.get('pdf_url')
        media_id = find_media_by_url(url)
        if media_id:
            media_ids.append(media_id)

    print(f"[DEBUG] Найденные media_ids: {media_ids}")
    return media_ids

def get_storage_limit(user: CustomUser) -> int:
    """
    Возвращает лимит хранилища пользователя в байтах.
    Если тариф не найден или неактивен — возвращает 0.
    """
    if not hasattr(user, 'tariff') or not user.tariff.is_active():
        return 0

    tariff_code = user.tariff.tariff_type
    tariff_data = settings.TARIFFS.get(tariff_code)
    if not tariff_data:
        return 0

    gb = tariff_data.get('memory_gb', 0)
    return int(gb * 1024**3)  # перевод в байты

@transaction.atomic
@require_POST
@ratelimit(key='ip', rate='15/m', block=True)
def taskSave(request, section_id):
    section_instance = get_object_or_404(Section, id=section_id)

    if request.user != section_instance.lesson.course.user:
        return JsonResponse({'success': False, 'error': 'У Вас нет доступа.'}, status=403)

    try:
        data = json.loads(request.body)
        obj_id    = data.get('obj_id')
        task_type = data.get('task_type')
        payloads  = data.get('payloads', {}) or {}

        title = payloads.get("title")
        if title:
            payloads["title"] = title[:200].strip()

        def looks_like_base64(s: str) -> bool:
            if not isinstance(s, str):
                return False
            if 'base64,' in s or s.startswith('data:'):
                return True
            s_clean = ''.join(s.split())
            return bool(re.fullmatch(r'[A-Za-z0-9+/=\s]+', s)) and len(s_clean) > 32

        embed_map = {'Image': 'image_url', 'Audio': 'audio_url', 'Pdf': 'pdf_url'}
        model_class = globals().get(task_type)
        if not model_class:
            return JsonResponse({'success': False, 'error': 'Неверный тип задания'}, status=400)

        media_to_attach = []

        if task_type in embed_map:
            target_field = embed_map[task_type]

            found_b64, found_key = None, None
            for key, val in payloads.items():
                if isinstance(val, str) and looks_like_base64(val):
                    found_b64, found_key = val, key
                    break

            old_url, task_obj = None, None
            if obj_id:
                task_obj = get_object_or_404(BaseTask, id=obj_id)
                content = task_obj.content_object
                old_url = getattr(content, target_field, None)

            if found_b64:
                if old_url:
                    removeFile(old_url, request.user)
                res = hashMediaFile(found_b64, request.user)
                if not res or not res.get('url'):
                    return JsonResponse({'success': False, 'error': 'Не удалось обработать base64'}, status=400)
                payloads[target_field] = res['url']
                if res.get('media_id'):
                    media_to_attach.append(str(res['media_id']))
                if found_key != target_field:
                    payloads.pop(found_key, None)
            else:
                provided_url = payloads.get(target_field)
                if provided_url:
                    found_media = MediaFile.objects.filter(user=request.user, file=provided_url).first()
                    if not found_media:
                        filename = urlparse(provided_url).path.split('/')[-1] if urlparse(provided_url).path else ''
                        candidates = MediaFile.objects.filter(user=request.user, file__endswith=filename)
                        for m in candidates:
                            if getattr(m.file, 'url', None) == provided_url or \
                               (m.file and m.file.name.endswith(filename)):
                                found_media = m
                                break
                    if not found_media:
                        return JsonResponse({'success': False,
                                             'error': f'URL для {target_field} не найден в хранилище'}, status=400)
                    media_to_attach.append(str(found_media.id))
                    payloads[target_field] = provided_url
                else:
                    if not obj_id:
                        return JsonResponse({'success': False, 'error': f'{target_field} обязателен'}, status=400)
                    if obj_id and not old_url:
                        return JsonResponse({'success': False, 'error': f'Нет старого файла для {target_field}'}, status=400)
                    payloads[target_field] = old_url
                    if task_obj:
                        old_media_qs = task_obj.media.all()
                        media_to_attach.extend([str(m.id) for m in old_media_qs])

        # --- storage calc ---
        json_size = len(json.dumps(payloads, ensure_ascii=False).encode('utf-8'))
        storage_limit = get_storage_limit(request.user)

        # --- UPDATE ---
        if obj_id:
            task_obj = get_object_or_404(BaseTask, id=obj_id)
            content = task_obj.content_object

            if request.user.used_storage - task_obj.size + json_size > storage_limit:
                return JsonResponse({'success': False, 'error': 'Превышен лимит'}, status=403)

            for k, v in payloads.items():
                setattr(content, k, v)
            content.save()

            task_obj.size = json_size
            task_obj.save()

            if media_to_attach:
                task_obj.media.set(MediaFile.objects.filter(id__in=media_to_attach))
            else:
                task_obj.media.clear()

            request.user.update_used_storage(-task_obj.size + json_size)

        # --- CREATE ---
        else:
            last_order = BaseTask.objects.filter(section=section_instance).aggregate(
                max_order=Max('order')
            )['max_order'] or 0

            if task_type in embed_map and not payloads.get(embed_map[task_type]):
                return JsonResponse({'success': False, 'error': f'{embed_map[task_type]} обязателен'}, status=400)

            content = model_class.objects.create(**payloads)

            task_obj = BaseTask.objects.create(
                section=section_instance,
                content_object=content,
                content_type=ContentType.objects.get_for_model(model_class),
                order=last_order + 1,
                size=json_size,
            )

            if media_to_attach:
                task_obj.media.set(MediaFile.objects.filter(id__in=media_to_attach))

            request.user.update_used_storage(json_size)

            # --- Create CoursePdf if PDF task ---
            if task_type == "Pdf":
                try:
                    pdf_url = payloads.get("pdf_url")
                    media_obj = None
                    if pdf_url:
                        filename = os.path.basename(pdf_url)
                        candidates = MediaFile.objects.filter(user=request.user, file__endswith=filename)
                        for m in candidates:
                            if m.file and m.file.name.endswith(filename):
                                media_obj = m
                                break

                    print(f"[taskSave] Найденный media_obj для PDF: {media_obj}")

                    if media_obj:
                        # проверяем, есть ли уже запись для этого курса и media
                        exists = CoursePdf.objects.filter(course=section_instance.lesson.course,
                                                          media=media_obj).exists()
                        if exists:
                            print("[taskSave] CoursePdf для этого файла уже существует, создание пропущено")
                        else:
                            course_pdf = CoursePdf.objects.create(
                                course=section_instance.lesson.course,
                                media=media_obj,
                                title=payloads.get("title") or "Без названия",
                                url=pdf_url
                            )
                            print(
                                f"[taskSave] CoursePdf создан успешно: id={course_pdf.id}, title={course_pdf.title}, url={course_pdf.url}")
                    else:
                        print("[taskSave] MediaFile для PDF не найден, CoursePdf не создан")

                except Exception as e:
                    import traceback
                    print(f"[taskSave] Exception while creating CoursePdf: {e}")
                    traceback.print_exc()

        return JsonResponse({'success': True, 'task_id': str(task_obj.id), 'section_id': str(section_id)})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Неверный JSON'}, status=400)
    except Exception:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': 'Ошибка сервера.'}, status=500)





"""
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif"]
MAX_UPLOAD_SIZE_IMAGES = 5*1024**2
ALLOWED_AUDIO_TYPES = ['audio/mpeg', 'audio/mp3', 'audio/wav']
MAX_UPLOAD_SIZE_AUDIO = 50*1024**2
ALLOWED_PDF_TYPES = ['application/pdf']
MAX_UPLOAD_SIZE_PDF = 80 * 1024 ** 2  # 100 MB

def add_or_increment_media(user: CustomUser, uploaded_file) -> MediaFile:
    # Если это ссылка, не сохраняем файл
    if isinstance(uploaded_file, str) and (uploaded_file.startswith('http://') or uploaded_file.startswith('https://')):
        return MediaFile.objects.create(
            file='',  # пустой файл
            size=0,
            hash='',
            usage=1
        )

    # 1. Хэшируем по чанкам и считаем размер
    hasher = hashlib.sha256()
    size = 0
    for chunk in uploaded_file.chunks():
        hasher.update(chunk)
        size += len(chunk)
    file_hash = hasher.hexdigest()
    uploaded_file.seek(0)

    # 2. Пытаемся получить или создать
    try:
        media = MediaFile.objects.get(hash=file_hash)
        media.usage += 1
        media.save(update_fields=['usage'])
        print("Обновленный media", media.usage)
    except MediaFile.DoesNotExist:
        media = MediaFile.objects.create(
            file=uploaded_file,
            size=size,
            hash=file_hash,
            usage=1
        )

    return media

def decrement_or_delete_media(media: MediaFile, user: CustomUser):
    if media.usage > 1:
        media.usage -= 1
        media.save(update_fields=['usage'])
        print("Обновленный media", media.usage)
    else:
        # последнее использование — удаляем файл и БД-запись
        size = media.size
        media.file.delete(save=False)
        media.delete()
        print("Удалили media")

def get_or_create_media(user: CustomUser, uploaded_file, subdir: str = None):
    # передаём файл в вашу функцию
    media = add_or_increment_media(user, uploaded_file)
    # файл считается "новым", если после add usage == 1
    created = (media.usage == 1)

    print(f"[TEST] SHA256 хэш файла: {media.hash}")
    print(f"[TEST] Размер файла: {media.size} байт")
    print(f"[TEST] usage после добавления: {media.usage}")

    return media, created

def get_unique_filename(original_name: str) -> str:
    ext = os.path.splitext(original_name)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return unique_name

@ratelimit(key='ip', rate='10/m', block=True)
def upload_image(request):
    if request.method != 'POST' or 'image' not in request.FILES:
        return JsonResponse({'error': 'Файл не передан'}, status=400)

    image = request.FILES['image']
    # Проверяем тип и размер
    if isinstance(image, str) or image.name.startswith('http://') or image.name.startswith('https://'):
        return JsonResponse({
            'success': True,
            'url': image.name,
        })

    if image.content_type not in ALLOWED_IMAGE_TYPES:
        return JsonResponse({'error': 'Неверный формат файла. Допустимы: JPG, PNG, GIF'}, status=400)
    if image.size > MAX_UPLOAD_SIZE_IMAGES:
        return JsonResponse({'error': 'Файл слишком большой. Максимум — 5 MB'}, status=400)

    try:
        # При сохранении файла в get_or_create_media теперь будет уникальное имя
        media, created = get_or_create_media(request.user, image, subdir='images')
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({
        'success': True,
        'media_id': media.id,
        'url': media.file.url,
        'message': created and 'Новый файл загружен' or 'Файл уже есть на сервере'
    })

@ratelimit(key='ip', rate='10/m', block=True)
def upload_audio(request):
    if request.method != 'POST' or 'audio' not in request.FILES:
        return JsonResponse({'error': 'Аудиофайл не передан'}, status=400)

    audio = request.FILES['audio']
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        return JsonResponse({'error': 'Неверный формат файла. Допустимы: MP3, WAV'}, status=400)
    if audio.size > MAX_UPLOAD_SIZE_AUDIO:
        return JsonResponse({'error': 'Файл слишком большой. Максимум — 50 MB'}, status=400)

    # Генерируем уникальное имя файла
    unique_name = get_unique_filename(audio.name)
    audio_file = ContentFile(audio.read(), name=unique_name)

    try:
        # Передаем уже с уникальным именем
        media, created = get_or_create_media(request.user, audio_file, subdir='audio')
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({
        'success': True,
        'media_id': media.id,
        'url': media.file.url,
        'message': created and 'Новое аудио загружено' or 'Аудио уже есть на сервере'
    })

@require_POST
@ratelimit(key='ip', rate='10/m', block=True)
def upload_pdf(request):
    if 'pdf' not in request.FILES:
        return JsonResponse({'error': 'Файл не передан'}, status=400)

    course_id = request.POST.get('courseId')
    if not course_id:
        return JsonResponse({'error': 'Не передан courseId'}, status=400)

    try:
        course_obj = Course.objects.get(id=course_id, user=request.user)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Курс не найден или нет прав'}, status=404)

    pdf = request.FILES['pdf']
    original_title = request.POST.get('title', pdf.name)

    if isinstance(pdf, str) or pdf.name.startswith(('http://', 'https://')):
        media = MediaFile.objects.create(file=pdf.name)
        course_pdf = CoursePdf.objects.create(
            course=course_obj,
            media=media,
            title=original_title,
            url=pdf.name
        )
        return JsonResponse({
            'success': True,
            'media_id': media.id,
            'course_pdf_id': course_pdf.id,
            'url': pdf.name,
            'message': 'Внешний PDF привязан к курсу'
        })

    if pdf.content_type not in ALLOWED_PDF_TYPES:
        return JsonResponse({'error': 'Неверный формат файла. Допустим только PDF'}, status=400)
    if pdf.size > MAX_UPLOAD_SIZE_PDF:
        return JsonResponse({
            'error': f'Файл слишком большой. Максимум — {MAX_UPLOAD_SIZE_PDF // (1024**2)} MB'
        }, status=400)

    # Используем функцию для генерации уникального имени файла
    unique_filename = get_unique_filename(pdf.name)
    pdf.name = unique_filename

    try:
        media, created = get_or_create_media(
            request.user,
            pdf,
            subdir='pdfs'
        )
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    course_pdf, pdf_created = CoursePdf.objects.get_or_create(
        course=course_obj,
        media=media,
        defaults={
            'title': original_title,
            'url': media.file.url
        }
    )

    return JsonResponse({
        'success': True,
        'media_id': media.id,
        'course_pdf_id': course_pdf.id,
        'url': media.file.url,
        'message': (
            'Новый PDF загружен и привязан к курсу' if created else
            ('PDF уже существовал, но привязан к курсу' if pdf_created else
             'PDF уже был загружен и привязан к курсу')
        )
    })

def delete_course_pdf(request, course_id, pdf_id):
    course_obj = get_object_or_404(Course, id=course_id)

    if course_obj.user != request.user:
        return HttpResponseForbidden("Вы не можете удалить этот PDF.")

    pdf = get_object_or_404(CoursePdf, id=pdf_id)

    # если нужно убедиться, что media относится к этому курсу
    if course_obj != pdf.course:
        return HttpResponseForbidden("PDF не принадлежит этому курсу.")

    pdf.delete()
    return redirect('lesson_list', course_id=course_obj.id)
"""

# Новая логика обработки заданий
def hashMediaFile(b64: str, user) -> dict | None:
    """
    Ищет MediaFile по SHA-256 хэшу данных из base64/data URI.
    Если найден — возвращает {'url': ..., 'size': 0, 'media_id': ...}.
    Если не найден — создаёт запись, привязывает к user и возвращает
    {'url': ..., 'size': real_size, 'media_id': ...}.
    В случае ошибки возвращает None.
    """
    if not b64:
        return None

    # Парсим data URI (если есть) и получаем mime и base64-часть
    m = re.match(r'\s*data:(?P<mime>[-\w.+/]+)?(?:;charset=[^;]+)?;base64,(?P<data>.+)',
                 b64, flags=re.I | re.S)
    if m:
        mime = m.group('mime') or None
        b64_data = m.group('data')
    else:
        mime = None
        b64_data = ''.join(b64.split())  # убираем переносы и пробелы

    # decode base64 (мягко, добавляя padding если нужно)
    try:
        blob = base64.b64decode(b64_data, validate=True)
    except Exception:
        try:
            padding = '=' * (-len(b64_data) % 4)
            blob = base64.b64decode(b64_data + padding)
        except Exception:
            return None

    # вычисляем sha256
    sha256 = hashlib.sha256(blob).hexdigest()

    # если есть запись с таким hash — вернуть её url и size=0
    try:
        existing = MediaFile.objects.filter(hash=sha256).first()
    except Exception:
        return None

    if existing:
        try:
            url = existing.file.url if existing.file else None
        except Exception:
            url = None
        return {'url': url, 'size': 0, 'media_id': str(existing.id)}

    # иначе — создаём новую запись (с обработкой гонки)
    # формируем имя файла, пытаемся угадать расширение по mime
    filename = uuid.uuid4().hex
    ext = None
    if mime:
        try:
            ext = mimetypes.guess_extension(mime)
        except Exception:
            ext = None
    filename = filename + (ext or '.bin')

    content = ContentFile(blob, name=filename)
    real_size = len(blob)

    try:
        with transaction.atomic():
            media = MediaFile(
                file=content,
                size=real_size,
                hash=sha256,
            )

            if hasattr(MediaFile, 'user') or 'user' in [f.name for f in MediaFile._meta.get_fields()]:
                setattr(media, 'user', user)

            user.update_used_storage(real_size)
            print("[USER STORAGE UPDATED]: ", real_size // 8 // 1024)

            # Сохраняем — в save() модели хэш не будет перезаписан, т.к. мы его выставили
            media.save()
    except IntegrityError:
        # другая воркер-процедура создала такую запись в параллели — достаём её
        media = MediaFile.objects.filter(hash=sha256).first()
        if not media:
            return None
    except Exception:
        return None

    try:
        url = media.file.url if media.file else None
    except Exception:
        url = None

    return {'url': url, 'size': media.size, 'media_id': str(media.id)}

def removeFile(media_url: str, user) -> dict:
    """
    Удаляет MediaFile и связанные CoursePdf, если файл используется только в одном задании.
    Если файл используется в нескольких заданиях — не удаляет.
    Возвращает подробный словарь результата.
    """
    if not media_url or not isinstance(media_url, str):
        return {'success': False, 'error': 'Неверный media_url'}

    try:
        parsed = urlparse(media_url)
        filename = os.path.basename(parsed.path) or ''
    except Exception:
        filename = ''

    media = None
    try:
        # Ищем медиафайл только для данного пользователя
        media_qs = MediaFile.objects.filter(user=user)
        media = media_qs.filter(file=media_url).first()

        if not media and filename:
            candidates = media_qs.filter(file__endswith=filename)
            for m in candidates:
                try:
                    if getattr(m.file, 'url', None) == media_url:
                        media = m
                        break
                    if m.file and m.file.name and m.file.name.endswith(filename):
                        media = m
                        break
                except Exception:
                    continue
    except Exception:
        return {'success': False, 'error': 'Ошибка при поиске MediaFile'}

    if not media:
        return {'success': False, 'error': 'MediaFile не найден для данного URL у этого пользователя'}

    # --- считаем уникальные BaseTask, где используется media ---
    try:
        task_ids = set()

        # a) через M2M BaseTask.media
        m2m_tasks = BaseTask.objects.filter(
            section__lesson__course__user=user,
            media=media
        ).values_list("id", flat=True)
        task_ids.update(m2m_tasks)

        # b) inline usage (Image/Audio/Pdf)
        def inline_task_ids(model_cls, url_field_name):
            ct = ContentType.objects.get_for_model(model_cls)
            q_exact = Q(**{url_field_name: media_url})
            if filename:
                q_name = Q(**{f"{url_field_name}__endswith": filename})
                model_qs = model_cls.objects.filter(q_exact | q_name)
            else:
                model_qs = model_cls.objects.filter(q_exact)

            if not model_qs.exists():
                return []

            ids = list(model_qs.values_list('id', flat=True))
            return BaseTask.objects.filter(
                section__lesson__course__user=user,
                content_type=ct,
                object_id__in=ids
            ).values_list("id", flat=True)

        for model_cls, field in [(Image, "image_url"), (Audio, "audio_url"), (Pdf, "pdf_url")]:
            task_ids.update(inline_task_ids(model_cls, field))

        total_count = len(task_ids)
        print(f"[removeFile] Найдено вхождений файла в заданиях: {total_count}")

    except Exception as e:
        return {'success': False, 'error': f'Ошибка при подсчёте вхождений файла: {e}'}

    # --- логика удаления ---
    if total_count > 1:
        return {
            'success': True,
            'deleted': False,
            'reason': 'Файл используется в нескольких заданиях',
            'occurrences': total_count
        }

    if total_count == 0:
        return {
            'success': True,
            'deleted': False,
            'reason': 'Файл не используется в заданиях этого пользователя',
            'occurrences': 0
        }

    # total_count == 1 → удаляем
    size = media.size or 0
    media_id = str(media.id)

    # --- удаляем связанные CoursePdf ---
    try:
        course_pdfs = CoursePdf.objects.filter(media=media)
        for pdf in course_pdfs:
            print(f"[removeFile] Удаляем CoursePdf: id={pdf.id}, title={pdf.title}")
            pdf.delete()
    except Exception as e:
        print(f"[removeFile] Ошибка при удалении CoursePdf: {e}")

    # --- удаляем сам MediaFile ---
    try:
        with transaction.atomic():
            try:
                if media.file:
                    media.file.delete(save=False)
                    print(f"[removeFile] Файл в хранилище удалён: {media.file.name}")
            except Exception as e:
                print(f"[removeFile] Ошибка при удалении файла из хранилища: {e}")

            media.delete()
            print(f"[removeFile] MediaFile удалён из БД: id={media_id}")

            try:
                if size:
                    user.update_used_storage(-size)
                    print(f"[removeFile] Освобождено место пользователя: {size} байт")
            except Exception as e:
                print(f"[removeFile] Ошибка при обновлении used_storage: {e}")

    except Exception as e:
        return {'success': False, 'error': f'Ошибка при удалении файла из БД/хранилища: {e}'}

    return {'success': True, 'deleted': True, 'media_id': media_id, 'freed': size}







def delete_task_handler(user: CustomUser, task: BaseTask):
    """
    Удаляет задание:
      - для медиа-заданий Audio, Pdf, Image вызывает removeFile для соответствующего URL;
      - вычитает размер задания из хранилища пользователя (task.size);
      - удаляет content_object и BaseTask.
    """
    # 1) Если задание содержит медиа в виде URL — удаляем через removeFile
    media_url_fields = {
        'Image': 'image_url',
        'Audio': 'audio_url',
        'Pdf': 'pdf_url',
    }

    task_type = task.content_type.model_class().__name__
    url_field = media_url_fields.get(task_type)
    if url_field:
        try:
            content = task.content_object
            media_url = getattr(content, url_field, None)
            if media_url:
                removeFile(media_url, user)
        except Exception:
            # логировать при необходимости
            pass

    # 2) Очищаем связи M2M с MediaFile
    task.media.clear()

    # 3) Вычитаем размер задания из хранилища пользователя
    try:
        user.update_used_storage(-task.size)
        print("Updated used storage by", -task.size)
    except Exception:
        pass

    # 4) Удаляем сам content_object
    content = task.content_object
    if content:
        content.delete()

    # 5) Удаляем из контекста lesson-а
    lesson_context = task.section.lesson.context or {}
    if str(task.id) in lesson_context:
        del lesson_context[str(task.id)]
        task.section.lesson.context = lesson_context
        task.section.lesson.save(update_fields=["context"])

    # 6) Удаляем BaseTask
    task.delete()


@require_http_methods(["DELETE"])
def delete_task(request, task_id):
    try:
        with transaction.atomic():
            task = get_object_or_404(BaseTask, id=task_id)
            course_obj = task.section.lesson.course

            if request.user != course_obj.user:
                return JsonResponse({"error": "У вас нет прав на удаление задания"}, status=403)

            section = task.section
            order_to_remove = task.order

            # Удаляем задание и освобождаем размер
            delete_task_handler(request.user, task)

            # Перенумеровываем оставшиеся задания
            remaining = BaseTask.objects.filter(
                section=section,
                order__gt=order_to_remove
            )
            for t in remaining:
                t.order -= 1
                t.save(update_fields=["order"])

            return JsonResponse({"success": True})

    except BaseTask.DoesNotExist:
        print(f"Task {task_id} not found")
        return JsonResponse({"error": "Задание не найдено"}, status=404)
    except Exception as e:
        print(e)
        return JsonResponse({"error": "Ошибка сервера."}, status=500)



def handle_request_validation(request):
    """Validate the incoming request method and user role"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST only'}, status=405)

    if request.user.role != 'teacher':
        return JsonResponse(
            {'status': 'error', 'message': 'Only teachers can generate requests'},
            status=403
        )
    return None

def parse_request_data(request):
    """Parse and validate request data"""
    data = json.loads(request.body)

    required_fields = ['lessonId', 'taskType']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    return {
        'lesson_id': data['lessonId'],
        'task_type': data['taskType'],
        'context_flag': data.get('context', False),
        'emoji': data.get('emoji', False),
        'quantity': data.get('quantity', 2),
        'fill_type': data.get('fillType', 'lexical'),
        'match_type': data.get('matchType', ''),
        'test_type': data.get('testType', 'auto'),
        'language': data.get('language', 'en'),
        'sentence_length': data.get('sentenceLength', 6),
        'user_query': data.get('query', ''),
        'image_data': data.get('image', None)
    }

@ratelimit(key='ip', rate='20/m', block=True)
def generate_request(request):
    """Запуск асинхронной генерации через Celery"""
    validation_error = handle_request_validation(request)
    if validation_error:
        return validation_error

    try:
        if not has_min_tokens(request.user, min_tokens=5):
            raise PermissionError("Недостаточно токенов для выполнения поиска")

        try:
            if hasattr(request.user, 'metrics'):
                request.user.metrics.tasks_generated_counter += 1
                request.user.metrics.save(update_fields=["tasks_generated_counter"])
        except Exception as e:
            # Логируем или просто пропускаем
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to increment tasks_generated_counter for user {request.user.id}: {e}")

        params = parse_request_data(request)
        task = generate_task_celery.delay(request.user.id, params)

        return JsonResponse({'task_id': task.id, 'status': 'pending'}, status=202)

    except PermissionError as e:
        return JsonResponse({"error": str(e)}, status=403)
    except Exception as e:
        print("Unexpected error:", e)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def get_task_status(request, task_id):
    """Получение статуса Celery задачи"""
    task_result = AsyncResult(task_id)
    response = {
        'task_id': task_id,
        'status': task_result.status,  # PENDING, STARTED, SUCCESS, FAILURE
        'result': task_result.result if task_result.status == 'SUCCESS' else None
    }
    return JsonResponse(response)






def handle_pdf_upload(request):
    """
    Принимает POST-запрос с PDF-файлом (file или base64), query и section_id.
    Запускает обработку в Celery (OCR + генерация заданий).
    Если is_new_section=true — клонирует раздел и запускает обработку для него.
    """
    try:

        # Чтение PDF данных
        pdf_file = request.FILES.get('file')
        if pdf_file:
            pdf_data = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        else:
            base64_str = request.POST.get('base64')
            if base64_str:
                pdf_base64 = base64_str
            else:
                print("handle_pdf_upload: Нет файла и base64 данных")
                return JsonResponse({'error': 'No file or base64 data provided'}, status=400)

        # Получение параметров
        query = request.POST.get('query', '')
        section_id = request.POST.get('section_id')
        is_new_section = request.POST.get('is_new_section', 'false').lower() == 'true'

        if not section_id:
            return JsonResponse({'error': 'Missing section_id'}, status=400)

        # Если нужно создать новый раздел
        if is_new_section:
            print("handle_pdf_upload: Создание нового раздела")
            with transaction.atomic():
                try:
                    original_section = Section.objects.get(id=section_id)
                    print(f"handle_pdf_upload: Оригинальный раздел найден: {original_section}")

                    # Проверка прав
                    if original_section.lesson.course.user != request.user:
                        print("handle_pdf_upload: Доступ запрещён")
                        return JsonResponse({'error': 'Permission denied'}, status=403)

                    # Создаём новый раздел
                    new_section = Section.objects.create(
                        lesson=original_section.lesson,
                        name="New Section",
                        type=original_section.type
                    )
                    print(f"handle_pdf_upload: Новый раздел создан с id={new_section.id}")

                    section_id = str(new_section.id)

                except Section.DoesNotExist:
                    print("handle_pdf_upload: Оригинальный раздел не найден")
                    return JsonResponse({'error': 'Original section not found'}, status=404)
                except Exception as e:
                    print(f"handle_pdf_upload: Ошибка при создании нового раздела: {e}")
                    return JsonResponse({'error': f'Error creating new section: {str(e)}'}, status=500)

        # Проверка доступа для существующего (или нового) раздела
        print(f"handle_pdf_upload: Получение раздела с id={section_id}")
        section_obj = get_object_or_404(Section, id=section_id)
        if section_obj.lesson.course.user != request.user:
            print("handle_pdf_upload: Доступ к разделу запрещён")
            return JsonResponse({'error': 'Access denied'}, status=403)

        # Запуск фоновой задачи
        print(f"handle_pdf_upload: Запуск задачи Celery для section_id={section_id}")
        task = process_pdf_section_task.delay(section_id, query, pdf_base64, request.user.id)

        # Возвращаем task_id для опроса статуса
        response_data = {
            "message": "Processing started",
            "task_id": task.id
        }

        response_data["res_section_id"] = section_id

        print(f"handle_pdf_upload: Возвращаем ответ с task_id={task.id}")
        return JsonResponse(response_data)

    except Exception as e:
        print(f"handle_pdf_upload: Внутренняя ошибка сервера: {str(e)}")
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)

def get_pdf_status_view(request, task_id):
    """Возвращает статус выполнения Celery-задачи и результат, если готово."""
    print(f"get_pdf_status_view: Запрос статуса задачи {task_id}")

    task_id_str = str(task_id)  # Принудительно привести к строке

    result = AsyncResult(task_id_str)

    response_data = {
        "task_id": task_id_str,
        "status": result.status,  # PENDING, STARTED, RETRY, FAILURE, SUCCESS
        "result": None,
    }

    if result.ready():
        try:
            task_result = result.get()
            # Проверяем, если результат — словарь с ошибкой, возвращаем статус error
            if isinstance(task_result, dict) and "error" in task_result:
                response_data["status"] = "error"
                response_data["result"] = {"error": task_result["error"]}
                print(f"get_pdf_status_view: Ошибка в результате задачи {task_id_str}: {task_result['error']}")
            else:
                response_data["result"] = task_result
                print(f"get_pdf_status_view: Результат задачи {task_id_str} получен")
        except Exception as e:
            print(f"get_pdf_status_view: Ошибка при получении результата задачи {task_id_str}: {e}")
            response_data["status"] = "error"
            response_data["result"] = {"error": str(e)}

    return JsonResponse(response_data)




@require_POST
@login_required
@ratelimit(key='ip', rate='10/m', block=True)
def separate_into_blocks(request):
    """
    POST-параметры (JSON):
        - course_id
        - section_id
        - section_type        (one of 'lexical','listening','reading','grammar','speaking','other')
        - create_new_section  (optional, bool)
        - new_section_name    (optional, str) — если создаётся новый раздел
    Возвращает JSON:
        { "status": "ok", "blocks": [[{task_dict},...], ...], "new_section_id": "<uuid>" }
    """
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "invalid json"}, status=400)

    course_id = body.get("course_id")
    section_id = body.get("section_id")
    section_type = body.get("section_type")
    create_new_section = bool(body.get("create_new_section", False))
    new_section_name = body.get("new_section_name")

    if not (course_id and section_id and section_type and request.user.is_authenticated):
        return JsonResponse({"error": "missing parameters"}, status=400)

    if request.user and request.user.is_authenticated:
        try:
            if hasattr(request.user, 'metrics'):
                request.user.metrics.sections_generated_counter += 1
                request.user.metrics.save(update_fields=["sections_generated_counter"])
        except Exception as e:
            # Логируем или просто пропускаем
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to increment tasks_generated_counter for user {request.user.id}: {e}")

    # проверяем курс и владельца
    course_obj = get_object_or_404(Course, id=course_id)
    if course_obj.user != request.user:
        return JsonResponse({"error": "forbidden"}, status=403)

    # проверяем секцию и что она принадлежит курсу
    section_obj = get_object_or_404(Section, id=section_id)
    if section_obj.lesson.course.id != course_obj.id:
        return JsonResponse({"error": "section does not belong to course"}, status=400)

    # опционально создаём новый раздел на том же уроке
    new_section_obj = None
    if create_new_section:
        lesson_obj = section_obj.lesson
        name = new_section_name or f"{section_type.capitalize()} (auto)"
        new_section_obj = Section.objects.create(
            lesson=lesson_obj,
            name="New Section 🔥",
            type="learning"
        )

    # получаем prefs
    prefs = UserAutogenerationPreferences.objects.filter(course_id=course_id).first()
    if not prefs:
        return JsonResponse({"error": "no prefs for course"}, status=400)

    task_types_map = {
        'lexical': prefs.task_types_lexical,
        'listening': prefs.task_types_listening,
        'reading': prefs.task_types_reading,
        'grammar': prefs.task_types_grammar,
        'speaking': prefs.task_types_speaking,
        'other': prefs.task_types_other,
    }

    selected_task_types = task_types_map.get(section_type, []) or []

    blockers = {"WordList", "Note", "Article", "Audio"}
    blocks = []
    current_block = []

    for tdict in selected_task_types:
        if not isinstance(tdict, dict):
            continue

        task_name = list(tdict.keys())[0]
        current_block.append(tdict)

        if task_name in blockers:
            # закрываем блок и начинаем новый
            blocks.append(current_block)
            current_block = []

    # если что-то осталось незакрытое
    if current_block:
        blocks.append(current_block)

    # удаляем пустые блоки (на всякий случай)
    blocks = [b for b in blocks if b]

    response = {
        "status": "ok",
        "blocks": blocks,
        "new_section_id": str(new_section_obj.id) if new_section_obj else None
    }
    return JsonResponse(response, status=200)

@login_required
@ratelimit(key='ip', rate='30/m', block=True)
def start_block_generation(request):
    if request.method != "POST":
        return JsonResponse({"error": "only POST allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        section_id = data.get("section_id")
        auto_context = data.get("auto_context", [])
        context_flag = data.get("context_flag", False)
        emoji_flag = data.get("emoji_flag", False)
        block = data.get("block", [])

        if not section_id or not isinstance(block, list):
            return JsonResponse({"error": "invalid input"}, status=400)

        section_obj = get_object_or_404(Section, id=section_id)
        lesson_id = section_obj.lesson.id

        task_ids = []
        for task in block:
            task_type = list(task.keys())[0]
            print(task)
            user_query = task.get(task_type, {}).get('user_query')

            params = {
                "task_type": task_type,
                "context_flag": context_flag,
                "emoji": emoji_flag,
                "auto_context": auto_context,
                "user_query": user_query,
                "lesson_id": lesson_id,  # обязательно передаём lesson_id
            }

            async_res = generate_task_celery.delay(request.user.id, params)
            task_ids.append(str(async_res.id))

        generation = Generation.objects.create(
            user=request.user,
            section_id=section_id,
            created_at=timezone.now(),
            status="pending",
            tasks=task_ids,
        )

        return JsonResponse({"generation_id": str(generation.id)})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def block_generation_status(request, generation_id):
    try:
        generation = Generation.objects.get(id=generation_id, user=request.user)
    except Generation.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)

    task_ids = generation.tasks or []
    if not task_ids:
        return JsonResponse({"error": "no tasks"}, status=400)

    results = []
    in_progress = False

    for tid in task_ids:
        res = AsyncResult(tid)
        if res.successful():
            # безопасная проверка, что результат содержит data
            result_data = res.result
            if isinstance(result_data, dict) and "data" in result_data:
                results.append(result_data["data"])
            else:
                results.append(result_data)
        elif res.failed():
            # пропускаем неудачные задачи
            continue
        else:
            in_progress = True

    if in_progress:
        if generation.status != "in_progress":
            generation.status = "in_progress"
            generation.save(update_fields=["status"])
        return JsonResponse({"status": "in_progress"}, status=200)

    if results:
        generation.status = "done"
        generation.save(update_fields=["status"])
        return JsonResponse({
            "status": "done",
            "results": results
        }, status=200)
    else:
        generation.status = "failed"
        generation.save(update_fields=["status"])
        return JsonResponse({"status": "failed"}, status=200)

@require_POST
def create_section(request):
    """
    Создает новый раздел для урока и возвращает его id
    """
    import json

    try:
        data = json.loads(request.body)
        lesson_id = data.get("lesson_id")
        section_name = data.get("name", "Новый раздел 🔥")
        section_type = data.get("type", "learning")
    except Exception:
        return JsonResponse({"error": "invalid input"}, status=400)

    # Получаем урок
    lesson_obj = get_object_or_404(Lesson, id=lesson_id)

    # Проверка прав: только владелец курса может создавать разделы
    if request.user != lesson_obj.course.user:
        return JsonResponse({"error": "permission denied"}, status=403)

    # Создаем новый раздел
    new_section = Section.objects.create(
        lesson=lesson_obj,
        name=section_name,
        type=section_type
    )

    return JsonResponse({"section_id": str(new_section.id)})

@login_required
@require_POST
@ratelimit(key='ip', rate='30/m', block=True)
def form_block(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
        task_type = body.get("task_type")
        section_id = body.get("section_id")
        data_list = body.get("data", [])
        auto_context = body.get("auto_context", "")

        if not task_type or not section_id or not isinstance(data_list, list):
            return JsonResponse({"error": "invalid input"}, status=400)

        section_obj = get_object_or_404(Section, id=section_id)
        created_tasks = []
        updated_auto_context = auto_context

        for item_idx, item_data in enumerate(data_list):
            try:
                # --- вызываем универсальную функцию
                try:
                    task_data = call_form_function(task_type, request.user, payload=item_data)
                except Exception as e:
                    logger.exception("call_form_function failed for %s item %s: %s", task_type, item_idx, e)
                    continue

                if not task_data or not isinstance(task_data, dict):
                    logger.warning("call_form_function returned invalid for %s item %s: %r", task_type, item_idx, task_data)
                    continue

                # --- создаём задание
                try:
                    task_instance = create_task_instance(request.user, task_type, task_data, section_obj)
                except Exception as e:
                    logger.exception("create_task_instance failed for %s item %s: %s", task_type, item_idx, e)
                    continue

                task_id = getattr(task_instance, "id", None)
                if not task_id:
                    logger.warning("create_task_instance returned no id for %s item %s: %r", task_type, item_idx, task_instance)
                    continue

                created_tasks.append({"task_id": task_id, "task_type": task_type})

                # --- обновляем контекст (если тип требует)
                if task_type in {"WordList", "Note", "Article", "Audio"}:
                    try:
                        updated_auto_context = update_auto_context(updated_auto_context, task_type, task_data)
                    except Exception as e:
                        logger.exception("update_auto_context failed for %s item %s: %s", task_type, item_idx, e)
                        # не фатально

            except Exception as outer_e:
                logger.exception("Unexpected error processing item %s for %s: %s", item_idx, task_type, outer_e)
                continue

        return JsonResponse({
            "task_ids": created_tasks,
            "auto_context": updated_auto_context
        }, status=200)

    except Exception as e:
        logger.exception("form_block failed")
        return JsonResponse({"error": str(e)}, status=500)

def standart_pattern(request, course_id):
    course_obj = get_object_or_404(Course, id=course_id)
    if request.user != course_obj.user:
        return JsonResponse({'error': 'You are not a teacher'})

    defaults = {
        "task_types_lexical": [
            {"WordList": {"user_query": "Составьте список из 15 распространенных слов или фраз с переводами на русский язык."}},
            {"MatchUpTheWords": {"user_query": "Создайте 10 пар слов и их переводов для упражнения на сопоставление."}},
            {"Unscramble": {"user_query": "Выберите 5 ключевых слов и дайте русскоязычные подсказки для их угадывания."}},
            {"MakeASentence": {"user_query": "Напишите 5 коротких предложений (по 5-7 слов каждое)."}},
            {"LabelImages": {"user_query": "Подберите 6 слов, подходящих для подписи изображений."}},
            {"FillInTheBlanks": {
                "user_query": "Напишите предложения с 7 пропусками для заполнения подходящими словами."}},
        ],
        "task_types_listening": [
            {"Audio": {
                "user_query": "Придумайте название и напишите монолог-сценарий подкаста (150 слов) по теме урока."}},
            {"TrueOrFalse": {
                "user_query": "Создайте 5 сложных утверждений типа 'верно/неверно' для аудирования."}},
        ],
        "task_types_reading": [
            {"Article": {"user_query": "Придумайте название и напишите текст для чтения (200+ слов) по теме урока."}},
            {"Test": {"user_query": "Составьте 5 вопросов на понимание прочитанного."}},
        ],
        "task_types_grammar": [
            {"Note": {
                "user_query": "Кратко объясните использование и цель грамматической темы (на русском с английскими примерами)."}},
            {"TrueOrFalse": {
                "user_query": "Создайте 4 утверждения 'верно/неверно' на русском для проверки понимания материала."}},
            {"Test": {"user_query": "Создайте 10 четких грамматических вопросов по теме урока."}},
            {"FillInTheBlanks": {
                "user_query": "Напишите 6 предложений с одним пропуском в каждом; укажите базовую форму глагола в скобках при необходимости."}},
        ],
        "task_types_speaking": [
            {"Note": {
                "user_query": "Создайте 10 вопросов-подсказок для диалога по теме урока."}},
            {"Note": {"user_query": "Создайте 3 открытых вопроса для монолога по теме урока."}},
        ],
        "task_types_other": [
            {"WordList": {"user_query": "Составьте список из 10 ключевых слов или фраз из урока."}},
            {"MatchUpTheWords": {"user_query": "Создайте 7 пар слов и переводов для повторения."}},
            {"FillInTheBlanks": {"user_query": "Напишите 6 предложений с пропусками для повторения лексики."}},
            {"Note": {"user_query": "Кратко суммируйте основную грамматическую тему с примерами."}},
            {"Test": {"user_query": "Создайте 6 четких грамматических вопросов по теме урока."}},
            {"Note": {"user_query": "Подведите итоги урока, используя эмодзи."}},
        ],
    }

    prefs, created = UserAutogenerationPreferences.objects.update_or_create(
        course=course_obj,
        defaults=defaults
    )

    return JsonResponse({'status': 'ok', 'created': created})




def call_form_function(task_type, user, payload):
    form_func_name = f"form{task_type}"
    if form_func_name not in globals():
        return {"status": "error", "error": f"form function for {task_type} not found"}
    form_func = globals()[form_func_name]

    return form_func(user, payload)

def formWordList(user, payload):
    """
    Преобразует сгенерированные данные для WordList в готовый словарь:
        {"title": str, "words": [{"word": str, "translation": str}, ...]}

    Допускаемые входы:
      - полный ответ от генерации: {'status': 'success', 'data': {...}}
      - уже извлечённый data: {'title': ..., 'words': [...]}

    Возвращает:
      - dict с полями title и words (список слов) при успехе
      - None при ошибке / несоответствии формата
    """
    try:
        # если нам передали обёртку {'status':..., 'data': {...}}
        if isinstance(payload, dict) and 'data' in payload and not ('title' in payload and 'words' in payload):
            data = payload.get('data')
        else:
            data = payload

        if not isinstance(data, dict):
            print(f"Ошибка: ожидается dict в data, получено {type(data)} -> {data}")
            return None

        title = data.get('title')
        if not isinstance(title, str):
            print(f"Ошибка: 'title' отсутствует или не строка: {title!r}")
            return None
        title = title.strip()

        words = data.get('words')
        if not isinstance(words, list):
            print(f"Ошибка: 'words' отсутствует или не список: {words!r}")
            return None

        cleaned_words = []
        for idx, item in enumerate(words):
            if not isinstance(item, dict):
                # пропускаем некорректные элементы
                print(f"Пропускаем элемент words[{idx}] — не dict: {item!r}")
                continue

            # ожидаемые ключи: 'word' и 'translation'
            w = item.get('word')
            t = item.get('translation')

            # небольшие корректировки / fallback: если нет ключей — пробуем похожие поля
            if w is None and 'text' in item:
                w = item.get('text')
            if t is None and 'translate' in item:
                t = item.get('translate')

            if isinstance(w, str):
                w = w.strip()
            if isinstance(t, str):
                t = t.strip()

            if isinstance(w, str) and w and isinstance(t, str) and t:
                cleaned_words.append({"word": w, "translation": t})
            else:
                print(f"Пропускаем некорректную пару в words[{idx}]: word={w!r}, translation={t!r}")

        return {"title": title, "words": cleaned_words}

    except Exception as e:
        # защитный падёж — возвращаем None и логируем
        print(f"Unexpected error in formWordList: {e}")
        return None

def _extract_data(payload):
    """
    Вспомогательная функция: если payload содержит 'data' — возвращаем payload['data'],
    иначе возвращаем payload (если это словарь).
    """
    if isinstance(payload, dict) and "data" in payload and not ("title" in payload and "words" in payload):
        return payload.get("data")
    return payload if isinstance(payload, dict) else None

def formMatchUpTheWords(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formMatchUpTheWords: data is not dict:", data)
        return None

    title = data.get("title")
    pairs = data.get("pairs")
    if not isinstance(title, str) or not isinstance(pairs, list):
        print("formMatchUpTheWords: invalid title or pairs")
        return None

    seen_card1 = set()
    seen_card2 = set()
    unique_pairs = []

    for idx, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            print(f"formMatchUpTheWords: pair[{idx}] is not dict: {pair!r}")
            continue
        # Accept if keys include card1 and card2 (may have extras) but require at least these
        if "card1" not in pair or "card2" not in pair:
            print(f"formMatchUpTheWords: pair[{idx}] missing keys: {pair!r}")
            continue

        card1 = pair.get("card1")
        card2 = pair.get("card2")

        if not isinstance(card1, str) or not isinstance(card2, str):
            print(f"formMatchUpTheWords: pair[{idx}] card types invalid: {pair!r}")
            continue

        if card1 in seen_card1 or card2 in seen_card2:
            # skip duplicates
            continue

        seen_card1.add(card1)
        seen_card2.add(card2)
        unique_pairs.append({"card1": card1.strip(), "card2": card2.strip()})

    if not unique_pairs:
        print("formMatchUpTheWords: no valid pairs")
        return None

    return {"title": title.strip(), "pairs": unique_pairs}

def formEssay(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formEssay: data is not dict:", data)
        return None

    title = data.get("title")
    conditions = data.get("conditions")

    if not isinstance(title, str):
        print("formEssay: invalid title")
        return None

    # conditions can be dict or list, accept both
    if conditions is not None and not isinstance(conditions, (dict, list)):
        print("formEssay: invalid conditions type")
        return None

    # normalize
    cleaned = {"title": title.strip()}
    if conditions is not None:
        cleaned["conditions"] = conditions

    return cleaned

def md_to_html(text: str) -> str:
    """
    Конвертирует Markdown-текст в HTML-теги.
    Поддерживает списки, таблицы, переносы строк и др.
    """
    return markdown.markdown(
        text,
        extensions=[
            "extra",        # таблицы, сноски и др.
            "nl2br",        # перевод \n в <br>
            "sane_lists"    # адекватная обработка списков
        ]
    )

def formNote(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formNote: data is not dict:", data)
        return None

    title = data.get("title")
    content = data.get("content")

    if not isinstance(title, str) or not isinstance(content, str):
        print("formNote: title/content must be strings")
        return None

    try:
        cleaned_content = md_to_html(content)
    except Exception as e:
        print("formNote: markdown_to_html failed:", e)
        cleaned_content = content

    return {"title": title.strip(), "content": cleaned_content}

def formArticle(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formArticle: data is not dict:", data)
        return None

    title = data.get("title")
    content = data.get("content")

    if not isinstance(title, str) or not isinstance(content, str):
        print("formArticle: invalid title or content")
        return None

    try:
        cleaned_content = md_to_html(content)
    except Exception as e:
        print("formArticle: markdown_to_html failed:", e)
        cleaned_content = content

    return {"title": title.strip(), "content": cleaned_content}

def formSortIntoColumns(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formSortIntoColumns: data is not dict:", data)
        return None

    title = data.get("title")
    columns = data.get("columns")

    if not isinstance(title, str) or not isinstance(columns, list):
        print("formSortIntoColumns: invalid title or columns")
        return None

    cleaned_columns = []
    for idx, col in enumerate(columns):
        if not isinstance(col, dict):
            print(f"formSortIntoColumns: column[{idx}] not dict: {col!r}")
            return None
        name = col.get("name")
        words = col.get("words")
        if not isinstance(name, str) or not isinstance(words, list):
            print(f"formSortIntoColumns: column[{idx}] invalid structure")
            return None
        # filter words to strings
        filtered_words = [w for w in words if isinstance(w, str)]
        cleaned_columns.append({"name": name.strip(), "words": filtered_words})

    return {"title": title.strip(), "columns": cleaned_columns}

def formFillInTheBlanks(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formFillInTheBlanks: data is not dict:", data)
        return None

    title = data.get("title")
    sentences = data.get("sentences")

    if not isinstance(title, str) or not isinstance(sentences, list):
        print("formFillInTheBlanks: invalid title or sentences")
        return None

    lines = []
    for idx, s in enumerate(sentences):
        if not isinstance(s, dict):
            print(f"formFillInTheBlanks: sentences[{idx}] is not dict: {s!r}")
            continue
        text = s.get("text")
        answer = s.get("answer")
        if not isinstance(text, str) or not isinstance(answer, str):
            print(f"formFillInTheBlanks: sentences[{idx}] invalid fields")
            continue

        # normalize underscores and insert answer in brackets
        safe_text = re.sub(r'_+', '_', text).strip()
        sentence = safe_text.replace("_", f"[{answer.strip()}]")
        try:
            html_line = markdown_to_html(sentence)
        except Exception:
            html_line = sentence
        lines.append(html_line)

    if not lines:
        print("formFillInTheBlanks: no valid sentences")
        return None

    full_text = "\n".join(lines)
    if not re.search(r"\[.+?\]", full_text):
        print("formFillInTheBlanks: no answers embedded")
        return None

    return {"title": title.strip(), "text": full_text}

def formTest(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formTest: data is not dict:", data)
        return None

    title = data.get("title")
    questions = data.get("questions")

    if not isinstance(title, str) or not isinstance(questions, list):
        print("formTest: invalid title or questions")
        return None

    clean_questions = []
    for qidx, q in enumerate(questions):
        if not isinstance(q, dict):
            print(f"formTest: question[{qidx}] not dict: {q!r}")
            continue
        text = q.get("text")
        answers = q.get("answers")
        if not isinstance(text, str) or not isinstance(answers, list):
            print(f"formTest: question[{qidx}] invalid fields")
            continue

        clean_answers = []
        for aidx, a in enumerate(answers):
            if not isinstance(a, dict):
                print(f"formTest: answer[{qidx}][{aidx}] not dict: {a!r}")
                continue
            ans_text = a.get("text")
            is_correct = a.get("is_correct")
            if not isinstance(ans_text, str) or not isinstance(is_correct, bool):
                print(f"formTest: answer[{qidx}][{aidx}] invalid")
                continue
            clean_answers.append({"text": ans_text.strip(), "is_correct": is_correct})

        if not clean_answers:
            print(f"formTest: question[{qidx}] has no valid answers")
            continue

        random.shuffle(clean_answers)
        clean_questions.append({"text": text.strip(), "answers": clean_answers})

    if not clean_questions:
        print("formTest: no valid questions")
        return None

    return {"title": title.strip(), "questions": clean_questions}

def formTrueOrFalse(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formTrueOrFalse: data is not dict:", data)
        return None

    title = data.get("title")
    statements = data.get("statements")

    if not isinstance(title, str) or not isinstance(statements, list):
        print("formTrueOrFalse: invalid title or statements")
        return None

    clean_statements = []
    for sidx, st in enumerate(statements):
        if not isinstance(st, dict):
            print(f"formTrueOrFalse: statements[{sidx}] not dict: {st!r}")
            continue
        text = st.get("text")
        is_true = st.get("is_true")
        if not isinstance(text, str) or not isinstance(is_true, bool):
            print(f"formTrueOrFalse: statements[{sidx}] invalid fields")
            continue
        clean_statements.append({"text": text.strip(), "is_true": is_true})

    if not clean_statements:
        print("formTrueOrFalse: no valid statements")
        return None

    return {"title": title.strip(), "statements": clean_statements}

def formLabelImages(user, payload):
    """
    Возвращает title и список images: [{'label': str, 'url': optional_str}, ...]
    URL назначается случайной картинкой из результатов search_images_api
    Логика:
        - Берем до 8 подписей
        - Для каждой пытаемся найти картинку
        - Как только найдено картинки для 6 подписей, прекращаем
        - Если найдено <2 картинок, вернуть None
    """
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formLabelImages: data is not dict:", data)
        return None

    title = data.get("title")
    labels = data.get("labels")

    if not isinstance(title, str) or not isinstance(labels, list):
        print("formLabelImages: invalid title or labels")
        return None

    cleaned = {"title": title.strip(), "images": []}

    # Фильтруем только строки и берем до 12 меток
    label_candidates = [lbl for lbl in labels if isinstance(lbl, str)]
    if not label_candidates:
        print("formLabelImages: no valid labels")
        return None

    if len(label_candidates) > 8:
        label_candidates = random.sample(label_candidates, 8)

    for lbl in label_candidates:
        url = None
        try:
            search_result = search_images_api(normalize(lbl, keep_emojis=False), user=user)
            images_list = search_result.get("images", [])
            if images_list:
                url = random.choice(images_list).get("url")
        except PermissionDenied:
            url = None
        except Exception as e:
            print(f"formLabelImages: error searching image for '{lbl}': {e}")
            url = None

        if url:
            cleaned["images"].append({"label": lbl.strip(), "url": url})

        # Завершаем, если уже нашли картинки для 6 меток
        if len(cleaned["images"]) >= 6:
            break

    # если найдено меньше 2 картинок → возвращаем None
    if len(cleaned["images"]) < 2:
        return None

    return cleaned

ALLOWED_AUDIO_MIME = {'audio/mpeg'}
ALLOWED_AUDIO_TEXT = 'mp3'
MAX_AUDIO_SIZE = 70 * 1024 * 1024

def formAudio(user, payload):
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formAudio: data is not dict:", data, "payload:", payload)
        return None

    title = data.get("title", "")
    transcript = data.get("transcript", "") or data.get("text", "") or ""

    try:
        transcript = clean_text(transcript) if transcript else ""
    except Exception:
        transcript = transcript or ""

    text = transcript or (title or "")
    if not text:
        print("formAudio: no text or transcript available")
        return None

    return {
        "title": title.strip() if isinstance(title, str) else "",
        "audio_url": "/media/uploads/notification.mp3",
        "transcript": transcript.strip()
    }

def clean_text(text):
    # Сначала удаляем эмодзи
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Затем обрезаем пробелы в начале и конце
    return text.strip()

def shuffle_word(word):
    if len(word) <= 1:
        return word
    word_letters = list(word)
    while True:
        random.shuffle(word_letters)
        shuffled = ''.join(word_letters)
        if shuffled != word:
            return shuffled

def formUnscramble(user, payload):
    """
    Ожидает data с keys 'title' и 'words' (words — list of dicts with 'word' and 'hint').
    Возвращает:
        {"title": str, "words": [{"word": str, "shuffled_word": str, "hint": str}, ...]}
    """
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formUnscramble: data is not dict:", data)
        return None

    title = data.get("title")
    words = data.get("words")

    if not isinstance(title, str):
        print("formUnscramble: invalid title")
        return None
    if not isinstance(words, list):
        print("formUnscramble: invalid words list")
        return None

    valid_items = [w for w in words if isinstance(w, dict)]
    if not valid_items:
        print("formUnscramble: no valid word items")
        return None

    sample_words = random.sample(valid_items, min(6, len(valid_items)))

    clean_words = []
    for idx, w in enumerate(sample_words):
        word = w.get("word")
        hint = w.get("hint", "") or w.get("translation", "")  # fallback
        if not isinstance(word, str):
            print(f"formUnscramble: sample[{idx}] word invalid: {w!r}")
            continue
        if not isinstance(hint, str):
            hint = ""

        # Очистка и шифровка
        try:
            clean_word = clean_text(word)
        except Exception:
            clean_word = word.strip()

        shuffled_word = shuffle_word(clean_word) if callable(globals().get("shuffle_word")) else "".join(random.sample(clean_word, len(clean_word))) if clean_word else ""
        clean_words.append({
            "word": clean_word,
            "shuffled_word": shuffled_word,
            "hint": hint.strip()
        })

    if not clean_words:
        print("formUnscramble: no clean words produced")
        return None

    return {
        "title": title.strip(),
        "words": clean_words
    }

def shuffle_sentence(sentence: str) -> str:
    words = sentence.strip().split()
    random.shuffle(words)
    shuffled = " ".join(words)
    return shuffled

def formMakeASentence(user, payload):
    """
    Ожидает data с keys 'title' и 'sentences' (list of dicts with 'sentence' key).
    Возвращает:
        {"title": str, "sentences": [{"correct": str, "shuffled": str}, ...]}
    """
    data = _extract_data(payload)
    if not isinstance(data, dict):
        print("formMakeASentence: data is not dict:", data)
        return None

    title = data.get("title")
    sentences = data.get("sentences")

    if not isinstance(title, str):
        print("formMakeASentence: invalid title")
        return None
    if not isinstance(sentences, list):
        print("formMakeASentence: invalid sentences")
        return None

    clean_sentences = []
    for idx, s in enumerate(sentences):
        if not isinstance(s, dict):
            print(f"formMakeASentence: sentences[{idx}] not dict: {s!r}")
            continue
        sentence = s.get("sentence") or s.get("text") or ""
        if not isinstance(sentence, str) or not sentence.strip():
            print(f"formMakeASentence: sentences[{idx}] invalid sentence")
            continue

        try:
            sentence = sentence.replace("\t", " ")
            corrected = clean_text(sentence)
            corrected = re.sub(r"\s+", " ", corrected).strip()
        except Exception:
            corrected = sentence.strip()

        if callable(globals().get("shuffle_sentence")):
            shuffled = shuffle_sentence(corrected)
        else:
            # fallback: simple word shuffle
            parts = re.split(r'(\s+)', corrected)
            words = [p for p in parts if not re.match(r'\s+', p)]
            spaces = re.findall(r'\s+', corrected)
            if not words:
                shuffled = corrected
            else:
                shuffled_words = random.sample(words, len(words))
                # naive reassembly (may lose original spacing but ok as fallback)
                shuffled = " ".join(shuffled_words)

        clean_sentences.append({
            "correct": corrected,
            "shuffled": shuffled
        })

    if not clean_sentences:
        print("formMakeASentence: no valid sentences")
        return None

    return {
        "title": title.strip(),
        "sentences": clean_sentences
    }




def create_task_instance(user, task_type, task_data, section_obj):
    if user is None:
        return None
    """
    Создаёт BaseTask с привязкой уже загруженных медиа-файлов,
    извлекаемых по URL из payloads, и считает общий размер в байтах.
    """
    from django.core.exceptions import ObjectDoesNotExist

    model_map = {
        "WordList": WordList,
        "MatchUpTheWords": MatchUpTheWords,
        "Essay": Essay,
        "Note": Note,
        "SortIntoColumns": SortIntoColumns,
        "MakeASentence": MakeASentence,
        "Unscramble": Unscramble,
        "FillInTheBlanks": FillInTheBlanks,
        "Article": Article,
        "Audio": Audio,
        "Test": Test,
        "TrueOrFalse": TrueOrFalse,
        "LabelImages": LabelImages,
    }

    if task_type not in model_map:
        raise ValueError(f"Unsupported task type: {task_type}")

    model_class = model_map[task_type]

    try:
        # 1. Создаём подмодель
        task_instance = model_class.objects.create(**task_data)
        content_type = ContentType.objects.get_for_model(model_class)

        # 2. Считаем JSON-часть
        json_body = json.dumps(task_data, ensure_ascii=False)
        json_size = len(json_body.encode("utf-8"))

        last_order = BaseTask.objects.filter(section=section_obj).aggregate(
            max_order=Max('order')
        )['max_order'] or 0

        # 3. Создаём BaseTask (size заполним позже)
        base_task = BaseTask.objects.create(
            section=section_obj,
            order=last_order + 1,
            content_type=content_type,
            object_id=task_instance.id,
            size=1
        )

    except Exception as e:
        print(f"[ERROR] Ошибка при создании задачи: {e}")
        raise

    try:
        # 4. Извлекаем media_ids из payloads
        media_ids = extract_media_ids(task_type, task_data)
    except Exception as e:
        print(f"[ERROR] Ошибка при извлечении media_ids: {e}")
        media_ids = []

    media_size = 0
    for mid in media_ids:
        try:
            media = MediaFile.objects.get(id=mid)
            media.usage += 1
            media.save(update_fields=["usage"])
            base_task.media.add(media)
            media_size += media.size
        except MediaFile.DoesNotExist:
            print(f"[WARNING] MediaFile с id={mid} не найден")
            continue
        except Exception as e:
            print(f"[ERROR] Ошибка при обработке media id={mid}: {e}")
            continue

    try:
        # 6. Подсчитываем общий размер и сохраняем
        total_size = json_size + media_size
        base_task.size = total_size
        base_task.save(update_fields=["size"])

        # 7. Обновляем квоту пользователя
        user.update_used_storage(total_size)
        print(f"[DEBUG] Updated user storage by: {total_size} байт")
    except Exception as e:
        print(f"[ERROR] Ошибка при финальном сохранении или обновлении квоты: {e}")

    return base_task

def save_autogen_preferences(request, course_id):
    if request.method == "POST":
        data = json.loads(request.body)
        try:
            course_obj = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return JsonResponse({"error": "Курс не найден"}, status=404)

        prefs, _ = UserAutogenerationPreferences.objects.get_or_create(course=course_obj)
        prefs.task_types_lexical = data.get('task_types_lexical', {})
        prefs.task_types_listening = data.get('task_types_listening', {})
        prefs.task_types_reading = data.get('task_types_reading', {})
        prefs.task_types_grammar = data.get('task_types_grammar', {})
        prefs.task_types_speaking = data.get('task_types_speaking', {})
        prefs.task_types_other = data.get('task_types_other', {})
        prefs.save()

        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "Invalid method"}, status=405)

def get_autogen_preferences(request, course_id):
    try:
        # Получаем курс
        course_obj = Course.objects.get(id=course_id)

        # Получаем или создаем настройки автогенерации
        prefs, created = UserAutogenerationPreferences.objects.get_or_create(course=course_obj)

        # Формируем ответ
        return JsonResponse({
            "task_types_lexical": prefs.task_types_lexical,
            "task_types_listening": prefs.task_types_listening,
            "task_types_reading": prefs.task_types_reading,
            "task_types_grammar": prefs.task_types_grammar,
            "task_types_speaking": prefs.task_types_speaking,
            "task_types_other": prefs.task_types_other,
        })

    except Course.DoesNotExist:
        return JsonResponse({"error": "Курс не найден"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)







def normalize(text: str, keep_emojis: bool = False) -> str:
    """Нормализует текст: разворачивает сокращения, удаляет пунктуацию (с возможностью сохранить эмодзи),
    убирает лишние пробелы, приводит к нижнему регистру.
    Заменяет различные виды кавычек, апострофов, запятых и точек на стандартные."""

    if not isinstance(text, str):
        return ''

    replacements = {
        # Апострофы и похожие знаки
        "‘": "'", "’": "'", "‛": "'", "ʼ": "'", "＇": "'", "`": "'",
        # Кавычки
        "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
        # Кавычки-ёлочки
        "‹": "'", "›": "'", "❮": '"', "❯": '"',
        # Запятые
        "‚": ",", "，": ",", "､": ",",
        # Точки
        "。": ".", "．": ".", "｡": ".",
        # Дефисы и тире (замена на дефис)
        "–": "-", "—": "-", "―": "-", "‑": "-",  # включая non-breaking hyphen
        # Пробелы (разные типы на обычный пробел)
        "\u00A0": " ",  # no-break space
        "\u2000": " ", "\u2001": " ", "\u2002": " ", "\u2003": " ",
        "\u2004": " ", "\u2005": " ", "\u2006": " ", "\u2007": " ",
        "\u2008": " ", "\u2009": " ", "\u200A": " ",
        "\u202F": " ", "\u205F": " ", "\u3000": " ",
        # Многоточия на точку
        "…": "...",
        # Символы процента, амперсанта и т.п. можно по желанию расширять
    }

    for orig, repl in replacements.items():
        text = text.replace(orig, repl)

    # Специальная замена для "won't" -> "will not"
    text = re.sub(r"\bwon't\b", "will not", text, flags=re.IGNORECASE)

    # Заменяем окончания n't на not
    text = re.sub(r"n't\b", " not", text, flags=re.IGNORECASE)

    # I'm -> I am
    text = re.sub(r"\bI'm\b", "I am", text, flags=re.IGNORECASE)

    # you're, we're, they're -> you are, we are, they are
    text = re.sub(r"\b(\w+)'re\b", r"\1 are", text, flags=re.IGNORECASE)

    # he's, she's, it's, what's, who's, where's, how's
    def replace_s(match):
        word = match.group(1).lower()
        if word in ['he', 'she', 'it', 'that', 'what', 'where', 'who', 'how', 'there']:
            return match.group(1) + " is"
        else:
            return match.group(1)

    text = re.sub(r"\b(\w+)'s\b", replace_s, text, flags=re.IGNORECASE)

    # let's -> let us
    text = re.sub(r"\blet's\b", "let us", text, flags=re.IGNORECASE)

    # Фильтрация символов
    if keep_emojis:
        emoji_pattern = r"[^\w\s" \
                        r"\U0001F600-\U0001F64F" \
                        r"\U0001F300-\U0001F5FF" \
                        r"\U0001F680-\U0001F6FF" \
                        r"\U0001F1E0-\U0001F1FF" \
                        r"\U00002700-\U000027BF" \
                        r"\U0001F900-\U0001F9FF" \
                        r"\U00002600-\U000026FF" \
                        r"\U00002B50" \
                        r"]+"
        text = re.sub(emoji_pattern, "", text)
    else:
        text = re.sub(r"[^\w\s]", "", text)

    # Заменяем множественные пробелы на один
    text = re.sub(r"\s+", " ", text)

    return text.strip().lower()

def handleLabelimagesAnswer(object, answer):
    """
    object.images = [
        {"url": "...", "label": "dance"},
        ...
    ]

    answer = {
        "image_index": 0,
        "label": "dance"
    }
    """
    try:
        image = object.images[answer['image_index']]
        return normalize(image['label'].strip()) == normalize(answer['label'].strip())
    except (IndexError, KeyError, AttributeError):
        return False

def handleMakeasentenceAnswer(object, answer):
    """
    answer = {
        sentenceIndex: 0,      # индекс предложения в списке
        word_index: 0,          # индекс слова в перемешанном (shuffled)
        gap_index: 2             # предполагаемая позиция в правильном (correct)
    }
    """
    sentence_index = answer['sentenceIndex']
    word_index = answer['word_index']
    gap_index = answer['gap_index']

    try:
        sentence_obj = object.sentences[sentence_index]
        correct_words = sentence_obj['correct'].split()
        shuffled_words = sentence_obj['shuffled'].split()

        if word_index >= len(shuffled_words) or gap_index >= len(correct_words):
            return False

        word_from_shuffled = shuffled_words[word_index]
        expected_word_in_correct = correct_words[gap_index]

        return normalize(word_from_shuffled, True) == normalize(expected_word_in_correct, True)
    except (IndexError, KeyError):
        return False

def handleUnscrambleAnswer(object, answer):
    """
    answer = {
        wordIndex: 0,      // индекс слова в списке
        letter_index: 0,      // индекс буквы в shuffled_word
        gap_index: 2         // предполагаемая позиция в правильном слове
    }
    """
    word_index = answer['word_index']
    gap_index = answer['gap_index']
    letter_index = answer['letter_index']

    try:
        target_word = object.words[word_index]
        correct_letter = target_word['word'][gap_index]
        provided_letter = target_word['shuffled_word'][letter_index]

        return normalize(correct_letter, True) == normalize(provided_letter, True)
    except (IndexError, KeyError):
        return False

def handleTestAnswer(task_object, answer):
    q_index = answer.get("qIndex")
    a_index = answer.get("aIndex")

    if not isinstance(q_index, int) or not isinstance(a_index, int):
        return False

    try:
        return bool(task_object.questions[q_index]["answers"][a_index]["is_correct"])
    except (IndexError, KeyError, TypeError):
        return False

def handleTrueFalseAnswer(task_object, answer):
    index = answer.get("statement_index")
    selected = answer.get("selected_answer", "").strip().lower()

    if not isinstance(index, int) or selected not in ["true", "false"]:
        return False

    try:
        correct = "true" if task_object["statements"][index]["is_true"] else "false"
        return selected == correct
    except (IndexError, KeyError, TypeError):
        return False

def handleFillintheblanksAnswer(object, answer):
    """
    content — HTML-строка с пропусками, например:
        'The [wolf] is a wild animal...'
    answer — словарь вида {'index': 0, 'answer': 'wolf'}
    """
    index = answer.get('index')
    user_input = answer.get('answer', '').strip()

    if index is None or not user_input:
        return False

    # Убираем HTML-теги и экранирование
    clean_text = unescape(re.sub(r'<[^>]+>', '', object.text))

    # Находим все пропуски в виде [word]
    correct_answers = re.findall(r'\[(.+?)\]', clean_text)

    if index >= len(correct_answers):
        return False

    # Нормализуем строки (без пунктуации, в нижнем регистре)
    correct_word = normalize(correct_answers[index])
    user_word = normalize(user_input)

    return user_word == correct_word

def handleMatchupthewordsAnswer(object, answer):
    """
    object — список словарей вида [{'card1': 'read', 'card2': 'читать'}, ...]
    answer — словарь вида {'card 1': 'read', 'card 2': 'читать'}
    """
    print(answer)
    card1 = answer.get('card 1')
    card2 = answer.get('card 2')

    for pair in object.pairs:
        if normalize(pair.get('card1'), True) == normalize(card1, True) and normalize(pair.get('card2'), True) == normalize(card2, True):
            return True
    return False

def handleSortintocolumnsAnswer(object, answer):
    column_name = answer.get('column_name')
    word = answer.get('word')

    is_correct = False
    for category in object.columns:
        if category['name'] == column_name:
            is_correct = word in category['words']
            break

    return is_correct

def check_answer(task_id, answer):
    task = get_object_or_404(BaseTask, id=task_id)
    task_type = task.content_type.model

    # Essay всегда считается правильным
    if task_type == "essay":
        return True

    # Имя обработчика из content_type (например, handleFillintheblanksAnswer)
    handler_name = f"handle{task_type.capitalize()}Answer"
    handler_func = globals().get(handler_name)

    if not callable(handler_func):
        return "undefined"

    return handler_func(task.content_object, answer)

def calculate_max_score(task_obj):
    """Вычисляет максимальный балл для задания на основе его типа и содержания"""
    content = task_obj.content_object
    task_type = task_obj.content_type.model

    if task_type == 'matchupthewords':
        return len(content.pairs)

    elif task_type == 'fillintheblanks':
        clean_text = unescape(re.sub(r'<[^>]+>', '', content.text))
        return len(re.findall(r'\[(.+?)\]', clean_text))

    elif task_type == 'test':
        return sum(1 for question in content.questions if any(ans['is_correct'] for ans in question['answers']))

    elif task_type == 'trueorfalse':
        return len(content.statements)

    elif task_type == 'labelimages':
        return len(content.images)

    elif task_type == 'unscramble':
        words = [word['word'] for word in content.words]
        total_length = sum(len(word) for word in words)  # Общая длина всех слов
        print(words, total_length)
        return total_length

    elif task_type == 'makeasentence':
        return sum(len(sentence['correct'].split()) for sentence in content.sentences)

    elif task_type == 'sortintocolumns':
        return sum(len(col['words']) for col in content.columns)

    return 10


def receiveComplexTestCheck(task_id, user_answer, content):
    try:
        print("[ComplexTest] start")

        if not user_answer.answer_data:
            print("[ComplexTest] no answers saved yet")
            return JsonResponse({
                'status': 'error',
                'message': 'No answers saved yet. Send individual answers first or sync state.',
                'expected': list(range(len(content.questions))),
                'received': []
            }, status=400)

        # dedupe — ожидаем, что values укажут на те же dict-ы, что в user_answer.answer_data
        cleaned_raw = deduplicate_by_index(user_answer.answer_data, 'qIndex') or {}
        cleaned = {int(k): v for k, v in cleaned_raw.items()}

        all_q_indexes = set(range(len(content.questions)))
        received_indexes = set(cleaned.keys())
        print(f"[ComplexTest] expected_indexes={sorted(all_q_indexes)}, received_indexes={sorted(received_indexes)}")
        if all_q_indexes != received_indexes:
            return JsonResponse({
                'status': 'error',
                'message': 'Not all questions answered',
                'expected': sorted(list(all_q_indexes)),
                'received': sorted(list(received_indexes))
            }, status=400)

        # Проверяем и обновляем записи in-place (не удаляем и не заменяем список)
        correct_count = 0
        incorrect_count = 0
        results = []

        for idx in sorted(cleaned.keys()):
            entry = cleaned[idx]  # предполагаем, что это ссылка на dict внутри user_answer.answer_data
            is_correct = handleTestAnswer(content, entry['answer'])
            entry['is_correct'] = is_correct
            entry['counted'] = True
            results.append(is_correct)
            if is_correct:
                correct_count += 1
            else:
                incorrect_count += 1

            # safety: если dedupe вернул копию (а не ссылку), обновим оригинал по сигнатурам
            if entry not in user_answer.answer_data:
                # ищем по timestamp -> заменяем/дополняем
                ts = entry.get('timestamp')
                replaced = False
                if ts:
                    for i, orig in enumerate(user_answer.answer_data):
                        if orig.get('timestamp') == ts:
                            user_answer.answer_data[i].update(entry)
                            replaced = True
                            break
                if not replaced:
                    # на худой конец — добавляем запись (сохраняем историю)
                    user_answer.answer_data.append(entry)

        user_answer.correct_answers = correct_count
        user_answer.incorrect_answers = incorrect_count
        user_answer.save()
        print("[ComplexTest] updated answer_data (kept history):", user_answer.answer_data)

        return JsonResponse({
            'status': 'success',
            'isCorrect': results,
            'task_id': task_id,
            'correct_count': correct_count,
            'incorrect_count': incorrect_count,
            'max_score': user_answer.max_score,
            'answer': [entry['answer'] for entry in user_answer.answer_data]  # возвращаем историю
        })

    except Exception as e:
        import traceback
        print("[ComplexTest] ERROR:", e)
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e), 'traceback': traceback.format_exc()}, status=500)


def receiveComplexTrueFalseCheck(task_id, user_answer, content):
    try:
        print("[ComplexTF] start")

        if not user_answer.answer_data:
            print("[ComplexTF] no answers saved yet")
            return JsonResponse({
                'status': 'error',
                'message': 'No answers saved yet. Send individual answers first or sync state.',
                'expected': list(range(len(content.statements))),
                'received': []
            }, status=400)

        cleaned_raw = deduplicate_by_index(user_answer.answer_data, 'index') or {}
        cleaned = {int(k): v for k, v in cleaned_raw.items()}

        all_indexes = set(range(len(content.statements)))
        received_indexes = set(cleaned.keys())
        print(f"[ComplexTF] expected_indexes={sorted(all_indexes)}, received_indexes={sorted(received_indexes)}")
        if all_indexes != received_indexes:
            return JsonResponse({
                'status': 'error',
                'message': 'Not all statements answered',
                'expected': sorted(list(all_indexes)),
                'received': sorted(list(received_indexes))
            }, status=400)

        results = []
        correct_count = 0
        incorrect_count = 0

        for idx in sorted(cleaned.keys()):
            entry = cleaned[idx]  # если это ссылка на оригинал — мы обновим его in-place
            try:
                val = entry['answer']['value']
            except Exception:
                return JsonResponse({'status': 'error', 'message': f'Invalid answer format for index {idx}'}, status=400)

            correct_value = content.statements[int(idx)]['is_true']
            is_correct = (str(val).lower() == str(correct_value).lower())

            entry['is_correct'] = is_correct
            entry['counted'] = True
            results.append(is_correct)

            if is_correct:
                correct_count += 1
            else:
                incorrect_count += 1

            # safety: если entry не тот же объект, обновим оригинал по timestamp или добавим
            if entry not in user_answer.answer_data:
                ts = entry.get('timestamp')
                replaced = False
                if ts:
                    for i, orig in enumerate(user_answer.answer_data):
                        if orig.get('timestamp') == ts:
                            user_answer.answer_data[i].update(entry)
                            replaced = True
                            break
                if not replaced:
                    user_answer.answer_data.append(entry)

        user_answer.correct_answers = correct_count
        user_answer.incorrect_answers = incorrect_count
        user_answer.save()
        print("[ComplexTF] updated answer_data (kept history):", user_answer.answer_data)

        return JsonResponse({
            'status': 'success',
            'isCorrect': results,
            'task_id': task_id,
            'correct_count': correct_count,
            'incorrect_count': incorrect_count,
            'max_score': user_answer.max_score,
            'answer': user_answer.answer_data
        })

    except Exception as e:
        import traceback
        print("[ComplexTF] ERROR:", e)
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e), 'traceback': traceback.format_exc()}, status=500)



def deduplicate_by_index(answer_data, key_name='index'):
    result = {}
    for entry in answer_data:
        ans = entry.get('answer', {})
        if isinstance(ans, dict) and key_name in ans:
            try:
                idx = int(ans[key_name])
                result[idx] = entry
            except (ValueError, TypeError):
                continue
    return result

def parse_request_body(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return None, JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    task_id = data.get('task_id')
    answer = data.get('answer')
    classroom_id = data.get('classroom_id')
    user_id = data.get('user_id')
    answer_type = data.get('type', 'fast')

    if not task_id or answer is None:
        return None, JsonResponse({'status': 'error', 'message': 'Missing task_id or answer'}, status=400)

    return {
        'task_id': task_id,
        'answer': answer,
        'classroom_id': classroom_id,
        'user_id': user_id,
        'type': answer_type
    }, None

def authorize_user(request_user, user_id, classroom_id, task_obj):
    # Получаем объект user и classroom
    user = get_object_or_404(User, id=user_id)
    classroom = None
    if classroom_id:
        classroom = get_object_or_404(Classroom, id=classroom_id)
        if request_user != user and request_user not in classroom.teachers.all() and request_user not in classroom.students.all():
            return None, None, JsonResponse({'status': 'error', 'message': 'Not authorized'}, status=403)
    else:
        # Доступ к курсу владельцу
        course_owner = task_obj.section.lesson.course.user
        if request_user != course_owner:
            return None, None, JsonResponse({'status': 'error', 'message': 'Unauthorized access'}, status=403)
    return user, classroom, None

from django.db import IntegrityError

def get_user_answer(user, classroom, task_obj):
    try:
        ua, _ = UserAnswer.objects.get_or_create(
            classroom=classroom,
            task=task_obj,
            user=user,
            defaults={
                'answer_data': [],
                'correct_answers': 0,
                'incorrect_answers': 0,
                'max_score': calculate_max_score(task_obj),
            }
        )
    except IntegrityError:
        ua = UserAnswer.objects.get(classroom=classroom, task=task_obj, user=user)
    return ua

def handle_fast_answer(task_id, answer, user_answer):
    timestamp = timezone.now().isoformat()
    is_correct = check_answer(task_id, answer)
    entry = {
        'answer': answer,
        'is_correct': is_correct,
        'timestamp': timestamp,
        'counted': False  # по задаче новый ответ не должен учитываться
    }

    # Удаляем первое вхождение такого ответа, если есть
    for i, e in enumerate(user_answer.answer_data):
        if e['answer'] == answer:
            del user_answer.answer_data[i]
            break

    # Добавляем новый (неучтённый) ответ
    user_answer.answer_data.append(entry)
    user_answer.save()
    return entry

def handle_plain_answer(answer, user_answer):
    timestamp = timezone.now().isoformat()
    print(answer)
    entry = {
        'answer': answer,
        'is_correct': 'undefined',
        'timestamp': timestamp,
        'counted': False
    }

    # Удаляем первое вхождение, если есть
    for i, e in enumerate(user_answer.answer_data):
        if e['answer'] == answer:
            del user_answer.answer_data[i]
            break

    # Добавляем новый неучтённый ответ
    user_answer.answer_data.append(entry)
    user_answer.save()
    return entry

@require_POST
@ratelimit(key='ip', rate='100/m', block=True)
def receiveAnswer(request):
    try:
        print("=== receiveAnswer START ===")
        print("Raw body:", request.body)
        print("Content-Type:", request.content_type)

        # 1) parse
        parsed, error = parse_request_body(request)
        if error:
            print("[STEP 1] Parse error")
            return error

        task_id = parsed['task_id']
        answer = parsed['answer']
        classroom_id = parsed.get('classroom_id')
        user_id = parsed.get('user_id')  # может быть None
        answer_type = parsed['type']
        print(f"[STEP 1] Parsed data → task_id={task_id}, type={answer_type}, user_id={user_id}, classroom_id={classroom_id}, answer={answer}")

        # 2) get task
        task_obj = get_object_or_404(BaseTask, id=task_id)
        print(f"[STEP 2] Task loaded (id={task_obj.id}, type={task_obj.content_type.model})")

        # 3) handle anonymous users
        user = get_object_or_404(User, id=user_id) if user_id else None
        if task_obj.section.lesson.is_public and not user:
            print("[STEP 3] Anonymous user mode")
            if answer_type == 'fast':
                is_correct = check_answer(task_id, answer)
                return JsonResponse({'status': 'success', 'isCorrect': is_correct, 'task_id': task_id,
                                     'received_answer': answer, 'correct_count': 0, 'incorrect_count': 0, 'max_score': 1})
            elif answer_type == 'plain':
                return JsonResponse({'status': 'success', 'isCorrect': True, 'task_id': task_id,
                                     'received_answer': answer, 'correct_count': 0, 'incorrect_count': 0, 'max_score': 1})
            else:
                print("[STEP 3] Unsupported answer type for anonymous:", answer_type)
                return JsonResponse({'status': 'error', 'message': 'Answer type not supported for anonymous users'}, status=400)

        # 4) authorize classroom
        classroom = None
        if classroom_id:
            try:
                classroom = Classroom.objects.get(id=classroom_id)
                print(f"[STEP 4] Classroom found id={classroom_id}")
            except Classroom.DoesNotExist:
                print(f"[STEP 4] Classroom not found id={classroom_id}")
                return JsonResponse({'status': 'error', 'message': 'Classroom not found'}, status=404)

        # 5) no classroom shortcut
        if not classroom:
            print("[STEP 5] No classroom mode")
            if answer_type in ['complex', 'plain']:
                return JsonResponse({'status': 'success', 'isCorrect': True, 'task_id': task_id,
                                     'received_answer': answer, 'correct_count': 0, 'incorrect_count': 0, 'max_score': 1})
            is_correct = check_answer(task_id, answer)
            return JsonResponse({'status': 'success', 'isCorrect': is_correct, 'task_id': task_id,
                                 'received_answer': answer, 'correct_count': 0, 'incorrect_count': 0, 'max_score': 1})

        # 6) get or create user_answer
        user_answer = get_user_answer(user, classroom, task_obj)
        # Нормализуем answer_data чтобы дальше безопасно работать
        if not user_answer.answer_data:
            user_answer.answer_data = []
        content = task_obj.content_object
        task_type = task_obj.content_type.model
        print(f"[STEP 6] UserAnswer created → task_type={task_type}, existing_saved={len(user_answer.answer_data)}")

        # 7) dispatch by type
        if answer_type == 'fast':
            print("[STEP 7] Fast answer")
            entry = handle_fast_answer(task_id, answer, user_answer)
        elif answer_type == 'plain':
            print("[STEP 7] Plain answer")
            entry = handle_plain_answer(answer, user_answer)
        elif answer_type == 'complex':
            print(f"[STEP 7] Complex answer dispatch → task_type={task_type}, answer={answer}")

            is_check = isinstance(answer, dict) and answer.get("flag") == "check"
            is_submission = isinstance(answer, dict) and ('index' in answer or 'qIndex' in answer)

            # если пришло сохранение (индекс) — сохраняем
            if is_submission:
                ans = answer if isinstance(answer, dict) else {'value': answer}
                entry = {
                    'answer': ans,
                    'timestamp': timezone.now().isoformat(),
                    'counted': False
                }
                if 'index' in ans:
                    entry['index'] = str(ans['index'])
                if 'qIndex' in ans:
                    entry['qIndex'] = str(ans['qIndex'])

                try:
                    # atomic + select_for_update для безопасности при конкурентных запросах
                    if getattr(user_answer, 'id', None):
                        with transaction.atomic():
                            ua = type(user_answer).objects.select_for_update().get(id=user_answer.id)
                            if not ua.answer_data:
                                ua.answer_data = []
                            ua.answer_data.append(entry)
                            ua.save()
                            saved_ua = ua
                    else:
                        # если объект новый без id – просто добавляем и сохраняем
                        user_answer.answer_data.append(entry)
                        user_answer.save()
                        saved_ua = user_answer

                    print(f"[STEP 7] Saved complex answer entry: {entry}")
                except Exception as e:
                    print("[STEP 7] Failed to save answer:", e)
                    traceback.print_exc()
                    return JsonResponse({'status': 'error', 'message': 'Failed to save answer'}, status=500)

                # если одновременно пришёл флаг check — продолжаем к проверке
                if is_check:
                    # обновим user_answer ссылку на свежие данные
                    ua_to_check = saved_ua
                    if task_type == 'test':
                        return receiveComplexTestCheck(task_id, ua_to_check, content)
                    elif task_type == 'trueorfalse':
                        return receiveComplexTrueFalseCheck(task_id, ua_to_check, content)
                    else:
                        print("[STEP 7] Unsupported complex task type:", task_type)
                        return JsonResponse({'status': 'error', 'message': 'Unsupported task type for complex check'}, status=400)

                # иначе просто подтверждаем сохранение
                return JsonResponse({
                    'status': 'success',
                    'message': 'Answer saved',
                    'saved_entry': entry,
                    'total_saved': len(saved_ua.answer_data)
                })

            # если пришёл только флаг check — запускаем проверку
            if is_check:
                if task_type == 'test':
                    return receiveComplexTestCheck(task_id, user_answer, content)
                elif task_type == 'trueorfalse':
                    return receiveComplexTrueFalseCheck(task_id, user_answer, content)
                else:
                    print("[STEP 7] Unsupported complex task type:", task_type)
                    return JsonResponse({'status': 'error', 'message': 'Unsupported task type for complex check'}, status=400)

            # не распознали payload
            print("[STEP 7] Unknown complex payload:", answer)
            return JsonResponse({'status': 'error', 'message': 'Unknown complex payload'}, status=400)
        else:
            print("[STEP 7] Unknown answer type:", answer_type)
            return JsonResponse({'status': 'error', 'message': 'Unknown answer type'}, status=400)

        # 8) общая отдача
        print("[STEP 8] Returning success response")
        return JsonResponse({
            'status': 'success',
            'isCorrect': entry['is_correct'],
            'task_id': task_id,
            'received_answer': answer,
            'correct_count': user_answer.correct_answers,
            'incorrect_count': user_answer.incorrect_answers,
            'max_score': user_answer.max_score
        })

    except Exception as e:
        print("=== receiveAnswer ERROR ===", str(e))
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e), 'traceback': traceback.format_exc()}, status=500)





@login_required
@ratelimit(key='ip', rate='100/m', block=True)
def getAnswers(request):
    try:
        task_id = request.GET.get('task_id')
        classroom_id = request.GET.get('classroom_id')
        user_id = request.GET.get('user_id')  # Получаем user_id из параметров запроса

        # Проверка обязательных параметров
        if not all([task_id, classroom_id, user_id]):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required parameters: task_id, classroom_id or user_id'
            }, status=400)

        # Получаем пользователя по user_id
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'User with id {user_id} does not exist'
            }, status=404)

        # Получаем объекты задачи и класса
        task_obj = get_object_or_404(BaseTask, id=task_id)
        task_type = task_obj.content_type.model
        classroom_obj = get_object_or_404(Classroom, id=classroom_id)

        if request.user != user and request.user not in classroom_obj.teachers.all() and request.user not in classroom_obj.students.all():
            return JsonResponse({
                'status': 'error',
                'message': 'User does not have access to this task'
            }, status=403)

        # Получаем запись UserAnswer или создаём новую, если не существует
        user_answer, created = UserAnswer.objects.get_or_create(
            user=user,
            task=task_obj,
            classroom=classroom_obj,
            defaults={
                'answer_data': [],
                'correct_answers': 0,
                'incorrect_answers': 0,
                'max_score': calculate_max_score(task_obj)
            }
        )

        # Формируем ответ
        if task_type in ["test", "trueorfalse"]:
            max_score = user_answer.correct_answers + user_answer.incorrect_answers
        else:
            max_score = user_answer.max_score + user_answer.incorrect_answers
        response_data = {
            'status': 'success',
            'user_id': user.id,
            'task_id': task_id,
            'classroom_id': classroom_id,
            'correct_answers': user_answer.correct_answers,
            'incorrect_answers': user_answer.incorrect_answers,
            'max_score': max_score,
            'answers_history': user_answer.answer_data,
            'last_updated': user_answer.updated_at.isoformat(),
            'is_new_record': created
        }

        return JsonResponse(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'details': traceback.format_exc()
        }, status=500)

def delete_answers(request):
    if request.method == 'POST':
        try:
            # Получаем данные из тела запроса
            data = json.loads(request.body)
            task_id = data.get('task_id')
            classroom_id = data.get('classroom_id')
            user_id = data.get('user_id')

            # Проверяем обязательные параметры
            if not all([task_id, classroom_id, user_id]):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Missing required parameters: task_id or classroom_id'
                }, status=400)

            # Получаем объекты задачи и класса
            task_obj = get_object_or_404(BaseTask, id=task_id)
            classroom_obj = get_object_or_404(Classroom, id=classroom_id)
            user = User.objects.get(id=user_id)

            if request.user != user and request.user not in classroom_obj.teachers.all() and request.user not in classroom_obj.students.all():
                return JsonResponse({
                    'status': 'error',
                    'message': 'You are not authorized to delete this answer.'
                }, status=403)

            # Фильтруем ответы по task_id и classroom_id
            answers_query = UserAnswer.objects.filter(
                task=task_obj,
                classroom=classroom_obj,
                user=user
            )

            # Удаляем найденные записи
            deleted_count, _ = answers_query.delete()

            # Формируем ответ
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully deleted {deleted_count} answer(s)',
                'deleted_count': deleted_count
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': str(e),
                'details': traceback.format_exc()
            }, status=500)

    else:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid request method. Use POST.'
        }, status=405)

def reorder_tasks(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            if not data.get('tasks'):
                return JsonResponse(
                    {"status": "error", "message": "Отсутствуют данные о задачах"},
                    status=400
                )

            with transaction.atomic():
                # Получаем все задачи одним запросом
                task_ids = [item['id'] for item in data['tasks']]
                existing_tasks = BaseTask.objects.filter(id__in=task_ids)
                existing_ids = set(str(task.id) for task in existing_tasks)

                task_to_check = existing_tasks[0]
                if task_to_check.section.lesson.course.user != request.user:
                    return JsonResponse(
                        {"status": "error", "message": "У вас нет доступа к данной задаче"},
                        status=403
                    )

                # Проверяем, что все задачи существуют
                for item in data['tasks']:
                    if str(item['id']) not in existing_ids:
                        return JsonResponse(
                            {"status": "error", "message": f"Задача {item['id']} не найдена"},
                            status=404
                        )

                # Обновляем порядок
                for item in data['tasks']:
                    BaseTask.objects.filter(id=item['id']).update(order=item['order'])

                return JsonResponse({"status": "success"})

        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": str(e)},
                status=400
            )

@ratelimit(key='ip', rate='30/m', block=True)
def edge_tts_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        payload = json.loads(request.body)
        text = payload.get('text', '')
        voice = payload.get('voice', 'en-US-JennyNeural')
        rate = payload.get('rate', '+0%')
        pitch = payload.get('pitch', '+0Hz')

        if not text or not (3 <= len(text) <= 5000):
            return JsonResponse({'error': 'Text must be 3–5000 chars'}, status=400)

        # Создаём celery-задачу
        task = generate_audio_task.delay(
            user_id=request.user.id,
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch
        )

        return JsonResponse({'task_id': task.id})

    except Exception as e:
        print("edge_tts_view error:", e)
        return JsonResponse({'error': str(e)}, status=500)

@require_GET
def edge_tts_status_view(request, task_id):
    # Преобразуем UUID в строку
    task_id_str = str(task_id)
    status = get_audio_task_generation_status(task_id_str)
    return JsonResponse(status)

def get_audio_task_generation_status(task_id):
    """
    Проверяет статус задачи генерации аудио.
    Возвращает dict с ключами: state, info (при наличии).
    """
    result = AsyncResult(task_id)
    response = {
        'state': result.state,
    }
    if result.state == states.FAILURE:
        response['error'] = str(result.info) if result.info else 'Unknown error'
    elif result.state == states.SUCCESS:
        response['result'] = result.result
    elif result.state == states.PENDING:
        response['info'] = 'Задача ожидает выполнения'
    else:
        response['info'] = result.info or ''
    return response




def check_classroom_access(request, classroom_obj):
    """
    Проверяет доступ к классу или созданию класса:
    - Для учеников: доступ только если первый учитель класса активен и имеет Premium/Maximum.
    - Для учителей: если у учителя 0 или 1 виртуальный класс — доступ разрешён даже при Free/Basic.
      Но если тариф есть и он неактивен (expired) — доступ запрещён.
      Если у учителя >1 классов и тариф Free/Basic (или нет тарифа) — показать страницу с тарифами.
    Возвращает None, если доступ разрешён, иначе - HttpResponse (render).
    """

    user = request.user

    # -----------------------
    # 1) Если пользователь — студент в этом классе: проверяем тариф первого учителя
    # -----------------------
    if classroom_obj and user in classroom_obj.students.all() and user not in classroom_obj.teachers.all():
        # Для студентов проверяем тариф первого учителя
        teachers = classroom_obj.teachers.all()
        if teachers:
            first_teacher = teachers[0]
            try:
                teacher_tariff = first_teacher.tariff
                if teacher_tariff and teacher_tariff.is_active() and teacher_tariff.tariff_type not in (TariffType.FREE,
                                                                                                        TariffType.BASIC):
                    return None
                else:
                    return render(request, 'access_error/teacher_tariff_required.html')
            except UserTariff.DoesNotExist:
                return render(request, 'access_error/teacher_tariff_required.html')
        return None

    # -----------------------
    # 2) Для учителя (или попытки создания класса) — считаем, сколько у него классов
    # -----------------------
    try:
        teacher_class_count = Classroom.objects.filter(teachers=user).count()
    except Exception:
        # на всякий случай — если не смогли определить модель класса
        teacher_class_count = 0

    # -----------------------
    # 3) Проверяем наличие записи о тарифе у пользователя
    # -----------------------
    try:
        tariff = user.tariff
    except UserTariff.DoesNotExist:
        # Если тарифной записи нет:
        #    - если у учителя 0 или 1 класса — разрешаем (поведение по требованию)
        #    - иначе — перенаправление к тарифам
        if teacher_class_count <= 1:
            return None
        return render(request, 'access_error/pricing_for_teacher.html')

    # -----------------------
    # 4) Если тариф есть, но он неактивен -> запрещаем (независимо от кол-ва классов)
    # -----------------------
    if not tariff.is_active():
        return render(request, 'access_error/upgrade_subscription.html')

    # -----------------------
    # 5) Тариф активен:
    #    - если у учителя 0 или 1 класса — разрешаем (даже если тариф Free/Basic)
    #    - иначе (у >1 классов): если тариф Free/Basic -> требуем оплату, иначе разрешаем
    # -----------------------
    if teacher_class_count <= 1:
        return None

    if tariff.tariff_type in (TariffType.FREE, TariffType.BASIC):
        return render(request, 'access_error/pricing_for_teacher.html')

    # Всё ок
    return None

@login_required
def choose_classroom(request, lesson_id):
    """Страница выбора класса с AJAX‑поддержкой."""
    lesson_instance = get_object_or_404(Lesson, id=lesson_id)

    # --- проверка тарифа пользователя через общую функцию ---
    resp = check_classroom_access(request, None)
    if resp:
        return resp
    # --------------------------------------

    if request.method == "POST":
        selected_class_id = request.POST.get("classroom_id")
        if selected_class_id:
            classroom = get_object_or_404(Classroom, id=selected_class_id)
            # проверяем, что пользователь — учитель этого класса
            if request.user not in classroom.teachers.all():
                return JsonResponse(
                    {"success": False, "message": "You are not a teacher of this classroom"},
                    status=403
                )
            classroom.lesson = lesson_instance
            classroom.save()
            return redirect("classroom_view", classroom_id=selected_class_id)
        return JsonResponse({"success": False})

    # GET — страница выбора
    classrooms = request.user.classroom_set.all()
    return render(request, 'choose_classroom.html', {
        'lesson': lesson_instance,
        'classrooms': classrooms,
    })


def can_user_create_a_classroom(user):
    """
    Проверяет, может ли пользователь создать новый класс.
    """
    try:
        tariff = user.tariff
    except AttributeError:
        # если тарифа нет, считаем что это free
        return Classroom.objects.filter(teachers=user).count() == 0

    # если тариф не активен или базовый (unpaid)
    if not tariff.is_active() or tariff.status == TariffStatus.UNPAID:
        return False

    # тариф бесплатный -> разрешаем только если нет классов
    if tariff.tariff_type == TariffType.FREE:
        return Classroom.objects.filter(teachers=user).count() == 0

    # тариф premium или maximum -> всегда True
    if tariff.tariff_type in [TariffType.PREMIUM, TariffType.MAXIMUM]:
        return True

    # по умолчанию запрещаем
    return False

# ----------------- функция с уроком -----------------
@login_required
@ratelimit(key='ip', rate='10/m', block=True)
def create_classroom_with_lesson(request, lesson_id):
    """
    Создание нового класса с привязанным уроком.
    """
    lesson_obj = get_object_or_404(Lesson, id=lesson_id)

    if not can_user_create_a_classroom(request.user):
        return render(request, 'access_error/pricing_for_teacher.html')

    classroom, errors = _create_classroom(request, lesson_obj=lesson_obj)
    if not classroom:
        # Ошибки формы
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"success": False, "errors": errors}, status=400)
        return render(request, 'classroom/create_classroom.html', {
            'form': ClassroomForm(request.POST or None),
            'lesson': lesson_obj
        })

    # Успех
    redirect_url = reverse("classroom_view", args=[classroom.id])
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({"success": True, "redirect_url": redirect_url})
    return redirect(redirect_url)


# ----------------- функция без урока -----------------
@login_required
@ratelimit(key='ip', rate='10/m', block=True)
def create_classroom_without_lesson(request):
    """
    Создание нового класса без привязанного урока.
    Возвращает JSON вместо шаблона.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Метод не разрешён"}, status=405)

    if not can_user_create_a_classroom(request.user):
        return JsonResponse({
            "success": False,
            "message": "Ваш тариф не позволяет создавать новые классы."
        }, status=403)

    classroom, errors = _create_classroom(request, lesson_obj=None)
    if not classroom:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse({
        "success": True,
        "message": "Класс успешно создан!",
        "redirect_url": reverse("classroom_view", args=[classroom.id])
    })


# ----------------- общая логика -----------------
def _create_classroom(request, lesson_obj=None):
    """
    Создание объекта Classroom.
    Возвращает (classroom, None) при успехе или (None, form.errors) при ошибке.
    """
    if request.method != 'POST':
        return None, {"method": "Метод не разрешён"}

    form = ClassroomForm(request.POST)
    if not form.is_valid():
        return None, form.errors

    classroom = form.save(commit=False)
    if lesson_obj:
        classroom.lesson = lesson_obj
    classroom.features = {"copying": True}  # по умолчанию
    classroom.save()
    classroom.teachers.add(request.user)

    return classroom, None

@login_required
@ratelimit(key='ip', rate='10/m', block=True)
def classroom_view(request, classroom_id):
    try:
        # Получение класса
        classroom_obj = get_object_or_404(Classroom, id=classroom_id)
        lesson_obj = classroom_obj.lesson

        # Проверка доступа по тарифу
        try:
            access_check = check_classroom_access(request, classroom_obj)
            if access_check:
                return access_check
        except Exception as e:
            logger.warning(f"Ошибка проверки доступа: {str(e)}")

        # Определение роли пользователя
        try:
            students = classroom_obj.students.all()
            teachers = classroom_obj.teachers.all()

            if request.user in teachers:
                user_role = "teacher"
            elif request.user in students:
                user_role = "student"
            else:
                return HttpResponseNotFound("Страница не найдена")
        except Exception as e:
            logger.error(f"Ошибка определения роли: {str(e)}")
            return HttpResponseServerError("Внутренняя ошибка сервера")

        # Обработка случая отсутствия урока
        if not lesson_obj:
            if user_role == "teacher":
                course_obj = getattr(classroom_obj, 'course', None)
                return render(
                    request,
                    'builder/updated_templates/select_lesson_placeholder.html',
                    {
                        'course': course_obj,
                        'classroom': classroom_obj
                    }
                )
            else:
                return HttpResponseNotFound("Страница не найдена")

        # Получение секций и задач
        try:
            sections = get_sorted_sections(lesson_obj)
            section_ids = [section.id for section in sections]

            section_ordering = Case(
                *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
                output_field=IntegerField()
            )

            tasks = (
                BaseTask.objects
                .filter(section__in=section_ids)
                .select_related('content_type')
                .annotate(section_order=section_ordering)
                .order_by('section_order', 'order')
            )
        except Exception as e:
            logger.error(f"Ошибка получения секций/задач: {str(e)}")
            return HttpResponseServerError("Внутренняя ошибка сервера")

        # Формирование структуры секций с задачами
        section_tasks = [
            {
                'id': sec.id,
                'section_title': sec.name,
                'tasks': [t for t in tasks if t.section_id == sec.id]
            }
            for sec in sections
        ]

        # Формирование ссылки приглашения (только для учителей)
        invitation_link = None
        if user_role == "teacher":
            try:
                invitation_link = request.build_absolute_uri(
                    reverse(
                        "accept_invitation",
                        args=[str(classroom_obj.invitation_code)]
                    )
                )
            except Exception as e:
                logger.error(f"Ошибка формирования ссылки: {str(e)}")

        return render(
            request,
            'builder/updated_templates/classroom.html',
            {
                'classroom_id': classroom_obj.id,
                'classroom': classroom_obj,
                'course_id': lesson_obj.course.id if lesson_obj and lesson_obj.course else None,
                'lesson': lesson_obj,
                'section_list': sections,
                'section_tasks': section_tasks,
                'students': students,
                'teachers': teachers,
                'user_role': user_role,
                'tasks': tasks,
                'mode': 'classroom',
                'user_id': request.user.id,
                "invitation_link": invitation_link,
                "user": request.user,
                "is_new": request.user.is_new,
            })
    except Exception as e:
        logger.error(f"Необработанная ошибка в classroom_view: {str(e)}")
        return HttpResponseServerError("Внутренняя ошибка сервера")

@login_required
def select_lesson_for_course(request, course_id):
    """
    Страница-плейсхолдер, когда для курса не выбран урок.
    Доступна только учителям класса, к которому принадлежит курс.
    """
    course_obj = get_object_or_404(Course, id=course_id)
    classroom = getattr(Course, 'classroom', None)

    if not classroom:
        return HttpResponseForbidden("Курс не привязан к классу.")

    # Проверяем, что пользователь — учитель этого класса
    if request.user not in classroom.teachers.all():
        return HttpResponseForbidden("Доступ только для учителей класса.")

    # При необходимости можно передать список существующих уроков/шаблонов
    context = {
        'course': course_obj,
        'classroom': classroom,
    }
    return render(request, 'builder/updated_templates/select_lesson_placeholder.html', context)

@require_POST
def delete_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    # Проверяем, что пользователь - учитель в этом классе
    if request.user not in classroom.teachers.all():
        return JsonResponse({'error': 'Недостаточно прав'}, status=403)

    try:
        with transaction.atomic():
            classroom.delete()
            return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def toggle_copying(request, classroom_id):
    if request.method == 'POST':
        try:
            # Получаем класс по ID
            classroom = Classroom.objects.get(id=classroom_id)

            if request.user not in classroom.teachers.all():
                return JsonResponse({
                    'success': False,
                    'error': 'У вас нет доступа к данному классу.'
                }, status=403)

            # Получаем данные из тела запроса
            data = json.loads(request.body)
            allow_copying = data.get('allow_copying')

            # Проверяем, что значение allow_copying было передано
            if allow_copying is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Параметр "allow_copying" отсутствует.'
                }, status=400)

            # Обновляем параметр features["copying"]
            classroom.features['copying'] = allow_copying
            classroom.save()

            # Возвращаем успешный ответ
            return JsonResponse({
                'success': True,
                'new_state': allow_copying
            })

        except ObjectDoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Класс не найден.'
            }, status=404)

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    # Если метод запроса не POST
    return JsonResponse({
        'success': False,
        'error': 'Метод не поддерживается.'
    }, status=405)

@login_required
@require_POST
@ratelimit(key='ip', rate='10/m', block=True)
def get_jitsi_token(request):
    try:
        data = json.loads(request.body)

        room = data.get('room', '*')
        user_role = data.get('role', 'student')  # например, 'teacher' или 'student'

        # Формируем payload для JWT
        payload = {
            "aud": "jitsi",
            "iss": "jitsi-linguaglow",
            "sub": "jitsi-linguaglow.ru",
            "room": room,
            "exp": int(time.time()) + 3600,
            "context": {
                "user": {
                    "name": request.user.username,
                    "email": request.user.email,
                    "moderator": user_role == "teacher"
                }
            }
        }

        token = jwt.encode(payload, settings.JITSI_APP_SECRET, algorithm="HS256")
        return JsonResponse({"token": token})

    except (json.JSONDecodeError, KeyError):
        return HttpResponseBadRequest("Invalid JSON data")

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def send_homework_page_view(request, classroom_id):
    classroom_obj = get_object_or_404(Classroom, id=classroom_id)
    lesson_obj = classroom_obj.lesson
    course_obj = lesson_obj.course
    if request.user != course_obj.user and not classroom_obj.teachers.filter(id=request.user.id).exists():
        return HttpResponseForbidden("You do not have access to this lesson.")

    sections = get_sorted_sections(lesson_obj)
    section_ids = [section.id for section in sections]

    # Создаём выражение для сортировки секций в нужном порядке
    section_ordering = Case(
        *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
        output_field=IntegerField()
    )

    tasks = BaseTask.objects.filter(section__in=section_ids) \
        .select_related('content_type') \
        .annotate(section_order=section_ordering) \
        .order_by('section_order', 'order')

    # Получаем домашки для данного класса и урока
    existing_homeworks = Homework.objects.filter(
        classroom=classroom_obj,
        lesson=lesson_obj,
    ).values_list('tasks__id', flat=True)

    existing_task_ids = set(existing_homeworks)
    existing_task_ids = [str(task_id) for task_id in existing_task_ids if task_id is not None]

    return render(request, 'builder/updated_templates/homework_select.html', {
        'lesson': lesson_obj,
        'tasks': tasks,
        'classroom': classroom_obj,
        'existing_task_ids': existing_task_ids,
    })


@require_POST
@ratelimit(key='ip', rate='10/m', block=True)
def send_homework(request):
    """
    Создаёт для каждого ученика в классе запись Homework
    со статусом 'sent' и привязывает задачи.
    Ожидает JSON { classroom_id: <uuid>, lesson_id: <uuid>, task_ids: [<uuid>, ...] }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Только POST")

    try:
        data = json.loads(request.body)
        classroom_id = data['classroom_id']
        lesson_id = data.get('lesson_id')
        task_ids = data.get('task_ids', [])
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Неверные данные")

    try:
        classroom = Classroom.objects.get(id=classroom_id)
    except Classroom.DoesNotExist:
        return HttpResponseBadRequest("Класс не найден")

    # Получаем задачи
    tasks = BaseTask.objects.filter(id__in=task_ids)

    students = classroom.students.all()  # если есть m2m students
    for student in students:
        hw, created_flag = Homework.objects.get_or_create(
            classroom=classroom,
            student=student,
            lesson_id=lesson_id,
            defaults={'status': 'sent', 'assigned_by': request.user}
        )
        hw.tasks.set(tasks)  # Связываем задачи в любом случае

    return JsonResponse({
        'created_count': len(hw.tasks.all()),
        'created_ids': [str(task.id) for task in hw.tasks.all()],
    })

@login_required
def homework_view(request, classroom_id, lesson_id):
    classroom_obj = get_object_or_404(Classroom, id=classroom_id)
    lesson_obj = get_object_or_404(Lesson, id=lesson_id)

    # Проверка общего доступа
    access_resp = check_classroom_access(request, classroom_obj)
    if access_resp:
        return access_resp

    # Разрешаем и учителю и ученику
    is_teacher = request.user in classroom_obj.teachers.all()
    is_student = request.user in classroom_obj.students.all()
    if not (is_teacher or is_student):
        return HttpResponseForbidden("У вас нет доступа к этому классу.")

    # Подбор домашки
    hw = None
    if is_student:
        try:
            hw = Homework.objects.get(
                classroom=classroom_obj,
                lesson=lesson_obj,
                student=request.user,
                status__in=['sent', 'resent', 'completed', 'checked']
            )
        except Homework.DoesNotExist:
            hw = None
    else:
        hw = Homework.objects.filter(
            classroom=classroom_obj,
            lesson=lesson_obj
        ).first()

    hw_tasks = hw.tasks.select_related('section').all() if hw else []
    section_ids = hw_tasks.values_list('section_id', flat=True).distinct()

    section_ordering = Case(
        *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
        output_field=IntegerField()
    )

    hw_tasks_res = BaseTask.objects.filter(section__in=section_ids) \
        .select_related('content_type') \
        .annotate(section_order=section_ordering) \
        .order_by('section_order', 'order')

    sections = [s for s in get_sorted_sections(lesson_obj) if s.id in section_ids]
    section_tasks = [
        {'id': s.id, 'section_title': s.name, 'tasks': [t for t in hw_tasks if t.section_id == s.id]}
        for s in sections
    ]

    return render(request, 'builder/updated_templates/homework.html', {
        'classroom_id': classroom_obj.id,
        'classroom': classroom_obj,
        'course_id': lesson_obj.course.id,
        'lesson': lesson_obj,
        'section_list': sections,
        'section_tasks': section_tasks,
        'tasks': hw_tasks_res,
        'mode': 'homework',
        'role': 'teacher' if is_teacher else 'student',
        'user_id': hw.student.id if hw else None,
        'students': classroom_obj.students.all(),
        'teachers': classroom_obj.teachers.all(),
        'status': hw.status if hw else None,
        'homework_student': hw.student if hw else None,
    })

@require_POST
@ratelimit(key='ip', rate='10/m', block=True)
def submit_homework(request):
    """
    Меняет статус Homework.
    Ожидает JSON: {
        classroom_id: <uuid>,
        lesson_id: <uuid>,
        status: 'resent' | 'completed' | 'checked'
    }
    Правила:
      - 'completed' может ставить ученик (request.user == hw.student)
      - 'resent' и 'checked' может ставить только учитель (request.user в classroom.teachers)
    """
    # 1. Разбор JSON
    try:
        data = json.loads(request.body)
        classroom_id = data['classroom_id']
        lesson_id = data.get('lesson_id')
        new_status = data['status']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Неверные данные")

    # 2. Проверка статуса
    valid_statuses = {'resent', 'completed', 'checked'}
    if new_status not in valid_statuses:
        return HttpResponseBadRequest(f"Неверный статус: {new_status}")

    # 3. Поиск записи
    hw = Homework.objects.filter(
        classroom_id=classroom_id,
        lesson_id=lesson_id
    ).select_related('classroom', 'student') \
     .first()

    if not hw:
        return HttpResponseBadRequest("Домашка не найдена")

    user = request.user

    # 4. Проверка прав
    if new_status in {'resent', 'checked'}:
        # Только учитель класса
        if not hw.classroom.teachers.filter(id=user.id).exists():
            return HttpResponseForbidden("Только учитель может изменить на этот статус")
    else:  # new_status == 'completed'
        # Только ученик, которому назначено это ДЗ
        if hw.student_id != user.id:
            return HttpResponseForbidden("Только ученик может отметить ДЗ как выполненное")

    # 5. Смена статуса и сохранение
    hw.status = new_status
    hw.save(update_fields=['status', 'updated_at'])

    return JsonResponse({
        'success': True,
        'new_status': hw.get_status_display()
    })





@login_required
def accept_invitation(request, code):
    """Обработка перехода по ссылке приглашения."""
    try:
        # Находим класс по коду приглашения
        classroom = get_object_or_404(Classroom, invitation_code=code)

        # Проверка: уже участник?
        if (request.user in classroom.students.all()) or (request.user in classroom.teachers.all()):
            return redirect("classroom_view", classroom_id=classroom.id)

        # Присоединяем пользователя как ученика
        classroom.students.add(request.user)

        messages.success(request, "Вы успешно присоединились к классу!")
        return redirect("classroom_view", classroom_id=classroom.id)

    except Classroom.DoesNotExist:
        messages.error(request, "Неверный код приглашения.")
        return redirect("dashboard")  # или другая безопасная страница

    except Exception as e:
        # Общий catch для всех неожиданных ошибок
        print(f"Error in accept_invitation: {e}")
        messages.error(request, "Произошла ошибка при присоединении к классу.")
        return redirect("dashboard")

def invitation_expired(request):
    return render(request, 'invitation_expired.html')

def invitation_not_found(request):
    return render(request, 'invitation_not_found.html')

def public_lesson_view(request, link_name):
    # ищем LessonPublicData по link_name
    public_data = get_object_or_404(LessonPublicData, link_name=link_name, lesson__is_public=True)
    lesson_obj = public_data.lesson
    course_obj = lesson_obj.course

    is_authenticated = request.user.is_authenticated
    sections = get_sorted_sections(lesson_obj)
    section_ids = [section.id for section in sections]

    section_ordering = Case(
        *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
        output_field=IntegerField()
    )

    tasks = BaseTask.objects.filter(section__in=section_ids) \
        .select_related('content_type') \
        .annotate(section_order=section_ordering) \
        .order_by('section_order', 'order')

    classrooms = ""
    if is_authenticated:
        classrooms = Classroom.objects.filter(
            Q(teachers=request.user) | Q(students=request.user)
        ).distinct()

    context = {
        "lesson": lesson_obj,
        "public_data": public_data,
        "section_list": sections,
        "user_id": request.user.id if is_authenticated else "",
        "course_id": course_obj.id,
        "is_authenticated": is_authenticated,
        "tasks": tasks,
        "classrooms": classrooms,
    }
    return render(request, "builder/public/public_resource.html", context)

@require_POST
@ratelimit(key='ip', rate='20/m', block=True)
def get_complex_tasks_answers(request):
    try:
        # 1) Парсинг JSON тела запроса
        body = json.loads(request.body)
        task_id = body.get("task_id")

        if not task_id:
            return JsonResponse({"error": "Missing task_id in request body."}, status=400)

        # 2) Получение задачи
        task_obj = get_object_or_404(BaseTask, id=task_id)
        content_type = task_obj.content_type
        content_object = task_obj.content_object

        # 3) Проверка публичности
        if not (task_obj.section.lesson.is_public or task_obj.section.lesson.course.user == request.user):
            return JsonResponse({"error": "Lesson is not public."}, status=403)

        # 4) Обработка типов задач
        if content_type.model_class() == Test:
            data = {
                "id": task_id,
                "answers": content_object.questions,
                "taskType": "test",
            }
        elif content_type.model_class() == TrueOrFalse:
            data = {
                "id": task_id,
                "answers": content_object.statements,
                "taskType": "trueorfalse",
            }
        else:
            return JsonResponse({"error": "Unsupported task type."}, status=400)

        return JsonResponse(data)

    except Exception as e:
        print("Error:", e)
        return JsonResponse({"error": str(e)}, status=500)



# Чтобы получить правильный ключ, сделай например маппинг:
from datetime import timedelta, date
from django.utils import timezone

period_map = {
    'month': 'price_month',
    '6mo': 'price_6mo',
    'year': 'price_year',
}

def get_old_tariff(user):
    """Возвращает старый тариф или None."""
    try:
        return user.tariff
    except UserTariff.DoesNotExist:
        return None

def calculate_lost_tokens(old, today):
    """Считает количество потерянных токенов при смене тарифа."""
    if not old or not old.reset_dates:
        return 0
    old_limit = settings.TARIFFS[old.tariff_type]['token_limit']
    remaining = sum(1 for d_str in old.reset_dates if date.fromisoformat(d_str) > today)
    return remaining * old_limit

def get_period_info(period):
    """Возвращает (длительность_в_днях, количество_циклов) для периода."""
    if period == 'month':
        return 30, 1
    elif period == '6mo':
        return 30 * 6, 6
    elif period == 'year':
        return 30 * 12, 12
    return 30, 1

def determine_status(old, new_type, period, total_days, today, price):
    """
    Определяет статус тарифа и возвращает кортеж:
    (status, payment_description)
    """
    if old and getattr(old, 'tariff_type', None) == new_type:
        # вычисляем days_left
        days_left = getattr(old, 'days_left', None)
        if days_left is None and getattr(old, 'end_date', None):
            end_dt = old.end_date
            end_date = end_dt.date() if hasattr(end_dt, 'date') else end_dt
            days_left = (end_date - today).days

        if days_left is not None and days_left < 7:
            # renew
            base_date = old.end_date.date() if hasattr(old.end_date, 'date') else old.end_date or today
            new_end = (base_date + timedelta(days=total_days)).isoformat()
            print(f"STATUS: renew — тариф '{new_type}' на период '{period}' будет продлён до {new_end}")
            return 'renew', f"Продление тарифа '{new_type}' до {new_end}"
        else:
            # connected
            if getattr(old, 'end_date', None):
                end_dt = old.end_date
                end_date_str = end_dt.date().isoformat() if hasattr(end_dt, 'date') else end_dt.isoformat()
                print(f"STATUS: connected — Ошибка: тариф '{new_type}' уже подключен до {end_date_str}")
                return 'connected', f"Тариф '{new_type}' уже активен до {end_date_str}"
            else:
                print(f"STATUS: connected — Ошибка: тариф '{new_type}' уже подключен (дата окончания неизвестна)")
                return 'connected', None
    else:
        # available
        available_end = (today + timedelta(days=total_days)).isoformat()
        price_str = str(price) if price is not None else "N/A"
        print(f"STATUS: available — тариф '{new_type}' на период '{period}' доступен. Цена: {price_str}. Будет действовать до {available_end} (от {today.isoformat()})")
        return 'available', f"Покупка тарифа '{new_type}' до {available_end}"

from yookassa import Configuration, Payment

from users.models import Payment as PaymentRecord, UserTokenBalance

Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
Configuration.debug = getattr(settings, "YOOKASSA_TEST_MODE", False)

logger = logging.getLogger(__name__)

def compute_tariff_reset_dates(period_start: datetime, period_end: datetime) -> list:
    """
    Возвращает список дат строками "YYYY-MM-DD" — даты сброса каждый месяц,
    начиная с первого месяца после period_start (т.е. следующая дата сброса)
    и до period_end.date() включительно (если попадает).
    """
    if not period_start or not period_end:
        return []

    start_date = period_start.date()
    end_date = period_end.date()

    dates = []
    # начинаем с первого сброса после начала — period_start + 1 месяц
    current = start_date + relativedelta(months=1)
    while current <= end_date:
        dates.append(current.strftime("%Y-%m-%d"))
        current += relativedelta(months=1)

    return dates

@ratelimit(key='ip', rate='10/m', block=True)
def connect_tariff(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden('auth_required')

    if request.method != 'POST':
        return HttpResponseBadRequest('Invalid method')

    try:
        data = json.loads(request.body)
        new_type = data['tariff_type']
        period = data.get('period', 'month')
        _ = settings.TARIFFS[new_type]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return HttpResponseBadRequest('Invalid data')

    user = request.user
    today = timezone.now().date()

    discounts = get_user_tariff_discounts(user)
    price_key = period_map.get(period)
    price = recount_tariff_prices(user, discounts).get(new_type, {}).get(price_key)
    full_price = recount_tariff_prices(user, discounts, consider_prepaid=False).get(new_type, {}).get(price_key)

    if price is None:
        logger.error("connect_tariff: price not found for %s %s", new_type, period)
        return JsonResponse({'status': 'error', 'message': 'price_not_found'}, status=400)

    old = get_old_tariff(user)
    lost_tokens = calculate_lost_tokens(old, today)
    total_days, cycles = get_period_info(period)
    status, payment_description = determine_status(old, new_type, period, total_days, today, price)

    if payment_description:
        logger.info("Tariff payment description: %s", payment_description)

    with transaction.atomic():
        payment_record = PaymentRecord.objects.create(
            user=user,
            payment_type=PaymentRecord.PaymentType.TARIFF,
            tariff_type=new_type,
            tariff_duration=(PaymentRecord.TariffDuration.MONTH if period == 'month'
                             else PaymentRecord.TariffDuration.SIX_MONTH if period == '6mo'
                             else PaymentRecord.TariffDuration.YEAR if period == 'year'
                             else period),
            amount=Decimal(str(price)),
            full_price=Decimal(str(full_price)),
            currency='RUB',
            status=PaymentRecord.Status.PENDING
        )

        try:
            return_path = '/payments/return/'
            return_url = request.build_absolute_uri(return_path) + f'?local_payment_id={payment_record.pk}'

            price_str = f"{Decimal(price):.2f}"
            payment_body = {
                "amount": {
                    "value": price_str,
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": payment_description or f"Подписка {new_type} ({period})",
                "metadata": {
                    "local_payment_id": str(payment_record.pk),
                    "user_id": str(user.id),
                    "tariff_type": new_type,
                    "tariff_period": period,
                },
                "receipt": {
                    "customer": {"email": user.email or ""},
                    "items": [
                        {
                            "description": payment_description or f"Подписка {new_type} ({period})",
                            "quantity": "1",
                            "amount": {"value": price_str, "currency": "RUB"},
                            "vat_code": getattr(settings, "YOOKASSA_DEFAULT_VAT_CODE", 1),
                            "payment_subject": "service",
                            "payment_mode": "full_prepayment"
                        }
                    ],
                    "tax_system_code": getattr(settings, "YOOKASSA_TAX_SYSTEM_CODE", 1)
                },
            }

            idempotence_key = str(uuid.uuid4())
            yk_payment = Payment.create(payment_body, idempotence_key)
        except requests.exceptions.RequestException as e:
            resp = getattr(e, 'response', None)
            detail = None
            if resp is not None:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
            logger.exception("YooKassa network error (connect_tariff): %s", detail or str(e))
            return JsonResponse({'status': 'error', 'message': 'payment_create_failed', 'detail': detail}, status=502)
        except Exception as e:
            detail = None
            try:
                candidate = e.args[0] if e.args else str(e)
                detail = candidate if isinstance(candidate, (dict, list)) else str(candidate)
            except Exception:
                detail = str(e)
            logger.exception("YooKassa create payment error (connect_tariff): %s", detail)
            return JsonResponse({'status': 'error', 'message': 'payment_create_failed', 'detail': detail}, status=500)

        transaction_id = getattr(yk_payment, 'id', None) or (yk_payment.get('id') if isinstance(yk_payment, dict) else None)
        if transaction_id:
            payment_record.transaction_id = transaction_id
            payment_record.save()

        confirmation_url = None
        try:
            conf = getattr(yk_payment, 'confirmation', None) or (yk_payment.get('confirmation') if isinstance(yk_payment, dict) else None)
            if isinstance(conf, dict):
                confirmation_url = conf.get('confirmation_url')
            else:
                confirmation_url = getattr(conf, 'confirmation_url', None)
        except Exception:
            confirmation_url = None

        if not confirmation_url:
            logger.error("connect_tariff: no confirmation_url in YooKassa response: %s", yk_payment)
            return JsonResponse({'status': 'error', 'message': 'no_confirmation_url'}, status=500)

        return JsonResponse({
            'status': 'ok',
            'payment_id': transaction_id,
            'local_payment_id': payment_record.pk,
            'confirmation_url': confirmation_url,
            'payment_description': payment_description,
            'computed_status': status
        })

@ratelimit(key='ip', rate='10/m', block=True)
def connect_tokens(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'unauthenticated', 'message': 'auth_required'}, status=401)

    if request.method != 'POST':
        return HttpResponseBadRequest('Invalid method')

    try:
        data = json.loads(request.body)
        amount = int(data['amount'])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return HttpResponseBadRequest('Invalid data')

    user = request.user
    available_packs = recount_token_prices(user)
    selected = next((p for p in available_packs if p['amount'] == amount), None)
    if not selected:
        return HttpResponseBadRequest('Pack not found')

    payment_description = f"Покупка {selected['amount']} токенов"

    with transaction.atomic():
        payment_record = PaymentRecord.objects.create(
            user=user,
            payment_type=PaymentRecord.PaymentType.TOKEN_PACK,
            token_amount=selected['amount'],
            amount=Decimal(str(selected['price'])),
            currency='RUB',
            status=PaymentRecord.Status.PENDING,
            full_price=Decimal(str(selected['price'])),
        )

        try:
            return_path = '/payments/return/'
            return_url = request.build_absolute_uri(return_path) + f'?local_payment_id={payment_record.pk}'

            price_str = f"{Decimal(selected['price']):.2f}"
            payment_body = {
                "amount": {
                    "value": price_str,
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": payment_description,
                "metadata": {
                    "local_payment_id": str(payment_record.pk),
                    "user_id": str(user.id),
                    "tokens": str(selected['amount'])
                },
                "receipt": {
                    "customer": {"email": user.email or ""},
                    "items": [
                        {
                            "description": payment_description,
                            "quantity": "1",
                            "amount": {"value": price_str, "currency": "RUB"},
                            "vat_code": getattr(settings, "YOOKASSA_DEFAULT_VAT_CODE", 1),
                            "payment_subject": "service",
                            "payment_mode": "full_prepayment"
                        }
                    ],
                    "tax_system_code": getattr(settings, "YOOKASSA_TAX_SYSTEM_CODE", 1)
                }
            }

            idempotence_key = str(uuid.uuid4())
            yk_payment = Payment.create(payment_body, idempotence_key)
        except requests.exceptions.RequestException as e:
            resp = getattr(e, 'response', None)
            detail = None
            if resp is not None:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
            logger.exception("YooKassa network error: %s", detail or str(e))
            return JsonResponse({'status': 'error', 'message': 'payment_create_failed', 'detail': detail}, status=502)
        except Exception as e:
            detail = None
            try:
                candidate = e.args[0] if e.args else str(e)
                if isinstance(candidate, (dict, list)):
                    detail = candidate
                else:
                    detail = str(candidate)
            except Exception:
                detail = str(e)
            logger.exception("YooKassa create payment error: %s", detail)
            return JsonResponse({'status': 'error', 'message': 'payment_create_failed', 'detail': detail}, status=500)

        transaction_id = getattr(yk_payment, 'id', None) or (yk_payment.get('id') if isinstance(yk_payment, dict) else None)
        if transaction_id:
            payment_record.transaction_id = transaction_id
            payment_record.save()

        confirmation_url = None
        try:
            conf = getattr(yk_payment, 'confirmation', None) or (yk_payment.get('confirmation') if isinstance(yk_payment, dict) else None)
            if isinstance(conf, dict):
                confirmation_url = conf.get('confirmation_url')
            else:
                confirmation_url = getattr(conf, 'confirmation_url', None)
        except Exception:
            confirmation_url = None

        if not confirmation_url:
            logger.error("No confirmation_url in YooKassa response: %s", yk_payment)
            return JsonResponse({'status': 'error', 'message': 'no_confirmation_url'}, status=500)

        return JsonResponse({
            'status': 'ok',
            'payment_id': transaction_id,
            'local_payment_id': payment_record.pk,
            'confirmation_url': confirmation_url,
            'payment_description': payment_description
        })

def _create_local_payment_from_yk(payment_obj):
    metadata = payment_obj.get('metadata') or {}
    user = None
    try:
        user_id = metadata.get('user_id')
        if user_id:
            User = get_user_model()
            user = User.objects.filter(id=int(user_id)).first()
    except Exception:
        user = None

    amount_obj = payment_obj.get('amount') or {}
    amount_value = amount_obj.get('value') or '0.00'
    currency = amount_obj.get('currency') or 'RUB'

    token_amount = None
    try:
        token_amount = int(metadata.get('tokens')) if metadata.get('tokens') else None
    except Exception:
        token_amount = None

    payment_record = PaymentRecord.objects.create(
        user=user,
        payment_type=PaymentRecord.PaymentType.TOKEN_PACK,
        token_amount=token_amount,
        amount=Decimal(str(amount_value)),
        currency=currency,
        status=PaymentRecord.Status.PENDING,
        transaction_id=payment_obj.get('id')
    )
    return payment_record

def check_user_pending_payments(user):
    """
    Проверяет pending платежи пользователя за последние сутки
    и обрабатывает их, если они оплачены
    """
    # Находим pending платежи за последние 24 часа
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)

    pending_payments = PaymentRecord.objects.filter(
        user=user,
        status=PaymentRecord.Status.PENDING,
        created_at__gte=twenty_four_hours_ago
    )

    processed_count = 0

    for payment in pending_payments:
        try:
            # Получаем актуальный статус из YooKassa
            yk_obj = Payment.find_one(payment.transaction_id)
            yk_status = getattr(yk_obj, 'status', None) or (yk_obj.get('status') if isinstance(yk_obj, dict) else None)

            if yk_status in ('succeeded', 'paid'):
                # Обрабатываем успешный платеж
                success = _safe_mark_completed_and_credit(payment)
                if success:
                    processed_count += 1
                    logger.info("Обработан pending платеж %s для пользователя %s",
                                payment.pk, user.id)

            elif yk_status == 'waiting_for_capture':
                # Пытаемся подтвердить платеж
                try:
                    idempotence_key = str(uuid.uuid4())
                    capture_body = {
                        "amount": {
                            "value": f"{payment.amount:.2f}",
                            "currency": payment.currency or "RUB"
                        }
                    }
                    capture_response = Payment.capture(payment.transaction_id, capture_body, idempotence_key)
                    captured_status = getattr(capture_response, 'status', None) or (
                        capture_response.get('status') if isinstance(capture_response, dict) else None)

                    if captured_status in ('succeeded', 'paid'):
                        success = _safe_mark_completed_and_credit(payment)
                        if success:
                            processed_count += 1
                            logger.info("Подтвержден и обработан pending платеж %s для пользователя %s",
                                        payment.pk, user.id)

                except Exception as e:
                    logger.exception("Ошибка capture для платежа %s: %s", payment.pk, str(e))

            elif yk_status in ('canceled', 'cancelled'):
                # Отменяем локально отмененный платеж
                payment.delete()
                logger.info("Отменен pending платеж %s для пользователя %s",
                           payment.pk, user.id)

        except Exception as e:
            logger.exception("Ошибка проверки pending платежа %s: %s", payment.pk, str(e))

    return processed_count

def _safe_mark_completed_and_credit(payment_record, provider_transaction_id=None):
    if payment_record.status == PaymentRecord.Status.COMPLETED:
        logger.info("Payment %s already completed — skipping", payment_record.pk)
        return True

    try:
        with transaction.atomic():
            payment_record.mark_completed(transaction_id=provider_transaction_id or payment_record.transaction_id)

            if payment_record.payment_type == PaymentRecord.PaymentType.TOKEN_PACK and payment_record.token_amount:
                balance, _ = UserTokenBalance.objects.get_or_create(
                    user=payment_record.user,
                    defaults={'tariff_tokens': 0, 'extra_tokens': 0}
                )
                balance.extra_tokens = (balance.extra_tokens or 0) + (payment_record.token_amount or 0)
                balance.save()
                logger.info("Credited %s tokens to user %s for payment %s",
                            payment_record.token_amount, payment_record.user.id, payment_record.pk)

            elif payment_record.payment_type == PaymentRecord.PaymentType.TARIFF:
                # Активируем тариф с передачей суммы оплаты
                success = activate_user_tariff(
                    payment_record.user,
                    payment_record.tariff_type,
                    payment_record.tariff_duration,
                    amount_paid=float(payment_record.amount),
                    full_price=float(payment_record.full_price),
                )
                if not success:
                    logger.error("Failed to activate tariff for payment %s", payment_record.pk)
                    return False

        return True

    except Exception as e:
        logger.exception("Error completing payment %s: %s", payment_record.pk, str(e))
        return False

def activate_user_tariff(
    user,
    tariff_type,
    duration,
    amount_paid=0,
    full_price=0,
    period_start: datetime = None,
    period_end: datetime = None
):
    """
    Активирует или продлевает тариф для пользователя и записывает reset_dates (tariff_dates).
    Если period_start/period_end переданы (например, из Payment), используем их — иначе
    считаем исходя из now и duration.
    """

    # Получаем конфигурацию тарифа
    tariff_config = settings.TARIFFS.get(tariff_type, {})
    tariff_tokens = tariff_config.get("token_limit", 0)

    # Определяем срок действия в месяцах
    if duration == PaymentRecord.TariffDuration.MONTH:
        months = 1
    elif duration == PaymentRecord.TariffDuration.SIX_MONTH:
        months = 6
    elif duration == PaymentRecord.TariffDuration.YEAR:
        months = 12
    else:
        months = 1  # по умолчанию месяц

    now = timezone.now()

    # Если period_start/period_end не переданы — вычисляем по now и months
    if period_start is None:
        period_start = now
    if period_end is None:
        period_end = period_start + relativedelta(months=months)

    # Считаем даты сброса
    reset_dates = compute_tariff_reset_dates(period_start, period_end)

    try:
        with transaction.atomic():
            user_tariff, created = UserTariff.objects.get_or_create(
                user=user,
                defaults={
                    "tariff_type": tariff_type,
                    "status": TariffStatus.ACTIVE,
                    "start_date": period_start,
                    "end_date": period_end,
                    "price_month": amount_paid / months if amount_paid > 0 else 0,
                    "months_left": months,
                    "reset_dates": reset_dates,
                },
            )

            if not created:
                # Пользователь уже имеет тариф
                if user_tariff.tariff_type == tariff_type:
                    # Продление того же тарифа
                    if user_tariff.end_date and user_tariff.end_date > now:
                        # Если тариф ещё активен — продлеваем от конца текущего
                        new_start_date = user_tariff.end_date
                        new_end_date = user_tariff.end_date + relativedelta(months=months)
                    else:
                        # Если тариф истёк — начинаем новый период от сегодня
                        new_start_date = now
                        new_end_date = now + relativedelta(months=months)

                    user_tariff.start_date = new_start_date
                    user_tariff.end_date = new_end_date
                    user_tariff.months_left = months
                    user_tariff.status = TariffStatus.ACTIVE

                    # пересчёт reset_dates от даты нового старта
                    user_tariff.reset_dates = compute_tariff_reset_dates(new_start_date, new_end_date)

                else:
                    # Смена на другой тариф — переинициализируем период и reset_dates
                    user_tariff.tariff_type = tariff_type
                    user_tariff.start_date = period_start
                    user_tariff.end_date = period_end
                    user_tariff.months_left = months - 1
                    user_tariff.status = TariffStatus.ACTIVE
                    user_tariff.price_month = full_price / months if full_price > 0 else 0
                    user_tariff.reset_dates = reset_dates

                user_tariff.save()

            else:
                # Уже установлен defaults с reset_dates
                user_tariff.end_date = period_end
                user_tariff.reset_dates = reset_dates
                user_tariff.save()

            # 🔹 Начисляем токены, если start_date сегодня или вчера
            if user_tariff.start_date.date() in {now.date(), (now - timedelta(days=1)).date()}:
                balance, _ = UserTokenBalance.objects.get_or_create(
                    user=user,
                    defaults={"tariff_tokens": 0, "extra_tokens": 0},
                )
                balance.tariff_tokens = tariff_tokens
                balance.save()

                logger.info(
                    "Начислено %s тарифных токенов пользователю %s (start_date=%s, сегодня=%s)",
                    tariff_tokens,
                    user.username,
                    user_tariff.start_date.date(),
                    now.date(),
                )
            else:
                logger.info(
                    "Токены пользователю %s не начислены, так как start_date=%s (сегодня=%s)",
                    user.username,
                    user_tariff.start_date.date(),
                    now.date(),
                )

            # Обновляем поле tariff_type в CustomUser
            user.tariff_type = tariff_type
            user.save()

            logger.info(
                "Тариф %s активирован для пользователя %s до %s (reset_dates=%s)",
                tariff_type,
                user.username,
                user_tariff.end_date,
                user_tariff.reset_dates,
            )

            return True

    except Exception as e:
        logger.exception(
            "Ошибка активации тарифа для пользователя %s: %s", user.username, str(e)
        )
        return False


@csrf_exempt
def tokens_return(request):
    payment_id = request.GET.get('paymentId') or request.GET.get('payment_id') or request.GET.get('id')
    local_id = request.GET.get('local_payment_id')

    payment_record = None
    yk_obj = None
    yk_status = None

    # Сначала ищем локальную запись платежа
    if local_id:
        try:
            payment_record = PaymentRecord.objects.filter(pk=int(local_id)).first()
        except (ValueError, TypeError):
            payment_record = None

    if payment_id and not payment_record:
        payment_record = PaymentRecord.objects.filter(transaction_id=payment_id).first()

    # Получаем актуальный статус от YooKassa
    if payment_record and payment_record.transaction_id:
        try:
            yk_obj = Payment.find_one(payment_record.transaction_id)
            yk_status = getattr(yk_obj, 'status', None) or (yk_obj.get('status') if isinstance(yk_obj, dict) else None)

            # Обрабатываем разные статусы
            if yk_status == 'waiting_for_capture':
                # Подтверждаем платеж, ожидающий capture
                try:
                    idempotence_key = str(uuid.uuid4())
                    capture_body = {
                        "amount": {
                            "value": f"{payment_record.amount:.2f}",
                            "currency": payment_record.currency or "RUB"
                        }
                    }
                    capture_response = Payment.capture(payment_record.transaction_id, capture_body, idempotence_key)
                    captured_status = getattr(capture_response, 'status', None) or (
                        capture_response.get('status') if isinstance(capture_response, dict) else None)

                    if captured_status in ('succeeded', 'paid'):
                        yk_status = captured_status
                        with transaction.atomic():
                            _safe_mark_completed_and_credit(payment_record)
                    else:
                        logger.info("Capture returned status %s for payment %s", captured_status, payment_record.pk)

                except Exception as e:
                    logger.exception("Error capturing payment %s: %s", payment_record.pk, str(e))

            elif yk_status in ('succeeded', 'paid'):
                # Платеж уже успешен - обрабатываем
                with transaction.atomic():
                    _safe_mark_completed_and_credit(payment_record)

        except requests.exceptions.RequestException as e:
            logger.exception("Network error fetching payment status from YooKassa: %s", str(e))
        except Exception as e:
            logger.exception("Error fetching payment status from YooKassa: %s", str(e))

    # Если не нашли платеж по transaction_id, пробуем создать из данных YooKassa
    if not payment_record and payment_id:
        try:
            if not yk_obj:
                yk_obj = Payment.find_one(payment_id)

            if yk_obj:
                payment_dict = yk_obj.to_dict() if hasattr(yk_obj, 'to_dict') else (
                    yk_obj if isinstance(yk_obj, dict) else {})
                payment_record = _create_local_payment_from_yk(payment_dict)
                yk_status = payment_dict.get('status')

                if yk_status in ('succeeded', 'paid'):
                    with transaction.atomic():
                        _safe_mark_completed_and_credit(payment_record)

        except Exception as e:
            logger.exception("Can't create local Payment from YooKassa object: %s", str(e))

    if not payment_record:
        logger.error("tokens_return: no local payment record found (payment_id=%s local_id=%s)", payment_id, local_id)
        return HttpResponseBadRequest("Payment not found")

    return render(request, 'payments/return.html', {
        'payment': payment_record,
        'provider_status': yk_status,
    })




def report_site_error(request):
    if request.method != "POST":
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)

        error_message = data.get('title', '') + "\n" + data.get('content', '')
        contacts = data.get('contacts', '').strip()

        # Если есть контакты, добавляем их к сообщению
        if contacts:
            error_message += f"\nКонтакты: {contacts}"

        function_name = data.get('function_name', '')[:255]  # обрезаем если слишком длинное

        # Создаем запись в базе
        SiteErrorLog.objects.create(
            error_message=error_message,
            function_name=function_name,
            created_at=timezone.now()
        )

        return JsonResponse({'detail': 'Сообщение об ошибке успешно сохранено'}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=500)


@login_required
@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def subscribe_emails(request):
    """
    Подписывает текущего пользователя на рассылку, ставит allow_emails = True
    """
    user = request.user

    if user.allow_emails:
        return JsonResponse({'status': 'already_subscribed', 'message': 'Вы уже подписаны на рассылку.'})

    user.allow_emails = True
    user.save()

    return JsonResponse({'status': 'success', 'message': 'Вы успешно подписаны на рассылку.'})

@login_required
@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def switch_role(request):
    user = request.user

    if user.role != Role.STUDENT:
        return JsonResponse({"error": "Only students can switch role"}, status=403)

    try:
        data = json.loads(request.body)

        # Меняем роль
        user.role = Role.TEACHER
        user.save()

        # Начисляем бонусы, как при регистрации
        extra_tokens = 200
        UserTokenBalance.objects.create(user=user, extra_tokens=extra_tokens, tariff_tokens=0)

        return JsonResponse({"success": True, "role": user.role})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_POST
def select_lesson(request):
    """
    Эндпоинт выбора урока для класса.
    Ожидает JSON { classroom_id, lesson_id }.
    Определяет публичный/личный урок по БД и передаёт в нужную функцию.
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    lesson_id = payload.get('lesson_id')
    classroom_id = payload.get('classroom_id')
    user = request.user

    if not lesson_id or not classroom_id:
        return JsonResponse({"status": "error", "message": "Missing lesson_id or classroom_id"}, status=400)

    # ищем lesson
    try:
        lesson_obj = Lesson.objects.select_related("course").get(id=lesson_id)
    except Lesson.DoesNotExist:
        raise Http404("Lesson not found")

    # ищем classroom
    try:
        classroom = Classroom.objects.get(id=classroom_id)
    except Classroom.DoesNotExist:
        raise Http404("Classroom not found")

    # маршрутизация
    print(lesson_obj.is_public)
    if lesson_obj.is_public:
        result = public_course_selection(request, user, classroom, lesson_obj)
    else:
        result = personal_course_selection(request, user, classroom, lesson_obj)

    return JsonResponse({
        "status": "ok",
        "data": result
    })


def public_course_selection(request, user, classroom, lesson_obj):
    """
    Логика выбора публичного урока:
    1) Получить/создать курс для пользователя "Transformed Lessons".
       Если создан - вызвать create_default_autogeneration_prefs(new_course).
    2) Если в курсе уже есть урок с таким названием - удалить его.
    3) Создать новый урок с таким же названием (is_public=False) в курсе.
    4) Создать в новом уроке столько разделов, сколько было в публичном уроке,
       и запустить clone_section(old_section, new_section, user) для каждого.
    5) Присвоить новый урок к classroom.lesson и сохранить.
    Возвращает dict с информацией или с ключом "error".
    """
    # Проверка: только учитель класса может выбирать урок
    if not classroom.teachers.filter(pk=user.pk).exists():
        return {
            "error": "forbidden",
            "message": "Только учителя класса могут выбирать урокы для него."
        }

    # имя курса для трансформированных публичных уроков (можно вынести в константу/настройки)
    transformed_course_name = "Transformed Lessons"

    # Работа в транзакции — если что-то упадёт, откатим изменения
    try:
        with transaction.atomic():
            # получить или создать курс
            user_course, created = Course.objects.get_or_create(
                user=user,
                name=transformed_course_name,
                defaults={"description": "Автоматически созданные трансформированные публичные уроки."}
            )

            if created:
                logger.info("Created transformed course for user %s: %s", user.pk, user_course.pk)
                if callable(create_default_autogeneration_prefs):
                    try:
                        create_default_autogeneration_prefs(user_course)
                    except Exception as e:
                        logger.exception("create_default_autogeneration_prefs failed for course %s: %s", user_course.pk, e)
                        # не критично — продолжаем, но логируем

            # Если в курсе уже есть урок с таким названием, удаляем его (и связанные секции через cascade)
            existing_lessons_qs = user_course.lessons.filter(name=lesson_obj.name)
            if existing_lessons_qs.exists():
                # Можно логировать какие удаляются
                existing_ids = list(existing_lessons_qs.values_list("id", flat=True))
                logger.info("Removing existing lessons %s in course %s for user %s", existing_ids, user_course.pk, user.pk)
                existing_lessons_qs.delete()

            # Создаём новый урок в курсе — делаем его не публичным (копия для пользователя)
            new_lesson = Lesson.objects.create(
                course=user_course,
                name=lesson_obj.name,
                is_public=False,
                context=lesson_obj.context or {}
            )

            # Клонируем секции
            with transaction.atomic():
                old_sections = list(lesson_obj.sections.all().order_by('id'))

                for old_sec in old_sections:
                    new_sec = Section.objects.create(
                        lesson=new_lesson,
                        name=old_sec.name,
                        type=old_sec.type,
                        order=old_sec.order,
                    )

                    if callable(clone_section):
                        try:
                            clone_section(old_sec, new_sec, user)
                        except Exception as e:
                            # Логируем ошибку и откатываем транзакцию
                            logger.exception("Ошибка клонирования раздела %s -> %s: %s",
                                             old_sec.pk, new_sec.pk, e)
                            raise  # Перебрасываем исключение для отката транзакции
                    else:
                        logger.warning("Функция клонирования недоступна — раздел %s создан без контента", new_sec.pk)

            # Привязываем новый урок к классу
            classroom.lesson = new_lesson
            classroom.save(update_fields=["lesson"])

            logger.info("Assigned new lesson %s to classroom %s", new_lesson.pk, classroom.pk)

            return {
                "message": f"Публичный урок '{lesson_obj.name}' преобразован и присвоен классу.",
                "lesson_id": str(new_lesson.id),
                "classroom_id": str(classroom.id),
                "course_id": str(user_course.id),
                "is_public": False
            }

    except Exception as e:
        # Общий обработчик ошибок
        logger.exception("Произошла ошибка при клонировании разделов: %s", e)
        return {
            "error": "clone_failed",
            "message": f"Произошла ошибка при клонировании: {str(e)}"
        }

    except Exception as exc:
        logger.exception("Unexpected error in public_course_selection: %s", exc)
        return {
            "error": "internal_error",
            "message": "Внутренняя ошибка при обработке публичного урока.",
            "details": str(exc)
        }


def personal_course_selection(request, user, classroom, lesson_obj):
    """
    Логика выбора личного урока.
    """
    # проверим что user владелец курса
    if lesson_obj.course.user != user:
        return {"error": "Вы не владелец этого урока"}

    classroom.lesson = lesson_obj
    classroom.save(update_fields=["lesson"])
    return {
        "message": f"Личный урок '{lesson_obj.name}' выбран для класса {classroom.id}",
        "lesson_id": str(lesson_obj.id),
        "classroom_id": str(classroom.id),
        "is_public": False
    }

def str_to_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    return False

@require_POST
def update_lesson(request, lesson_id):
    """
    Обновление урока.
    staff может менять все поля + pdf; обычный пользователь — только имя.
    """
    user = request.user
    lesson_obj = get_object_or_404(Lesson, id=lesson_id)

    # Определяем payload: если JSON — парсим, иначе используем request.POST
    payload = {}
    try:
        if request.content_type and request.content_type.startswith("application/json"):
            payload = json.loads(request.body.decode("utf-8") or "{}")
        else:
            # multipart/form-data или application/x-www-form-urlencoded
            payload = request.POST.dict()
    except Exception:
        payload = request.POST.dict()

    # --- обычный пользователь: только имя ---
    if not user.is_staff:
        new_name = (payload.get("name") or "").strip()
        if not new_name:
            return JsonResponse({"error": "Имя не может быть пустым"}, status=400)
        lesson_obj.name = new_name
        lesson_obj.save(update_fields=["name"])
        return JsonResponse({"name": lesson_obj.name})

    # --- staff: общие поля ---
    lesson_obj.name = payload.get("name", lesson_obj.name)
    # str_to_bool — оставляем как у тебя
    lesson_obj.is_public = str_to_bool(payload.get("is_public", lesson_obj.is_public))
    lesson_obj.save(update_fields=["name", "is_public"])

    # Получаем/создаём LessonPublicData
    public_data, _ = LessonPublicData.objects.get_or_create(lesson=lesson_obj)
    public_data.icon = payload.get("icon", public_data.icon)
    public_data.level = payload.get("level", public_data.level)
    public_data.lexical_topics = payload.get("lexical_topics", public_data.lexical_topics)
    public_data.grammar_topics = payload.get("grammar_topics", public_data.grammar_topics)
    public_data.extra_topics = payload.get("extra_topics", public_data.extra_topics)
    public_data.meta_description = payload.get("meta_description", public_data.meta_description)
    public_data.keywords = payload.get("keywords", public_data.keywords)

    # --- Работа с PDF ---
    # Фронтенд отправляет FormData -> файл окажется в request.FILES
    uploaded_pdf = request.FILES.get("pdf_file")
    # флаг удаления может прийти как '1' или 'true' и т.д.
    remove_pdf_flag = str(payload.get("remove_pdf", "")).lower() in ("1", "true", "on", "yes")

    if uploaded_pdf:
        # Базовая валидация: тип и (опционально) размер
        content_type = getattr(uploaded_pdf, "content_type", "")
        if content_type != "application/pdf":
            return JsonResponse({"error": "Разрешены только PDF файлы"}, status=400)

        # опционально: лимит по размеру (пример 10 MB)
        max_bytes = 10 * 1024 * 1024
        if uploaded_pdf.size > max_bytes:
            return JsonResponse({"error": "Файл слишком большой (макс 10 MB)"}, status=400)

        # Удаляем старый файл (если есть) — не сохраняем модель пока не присвоим новый файл
        if public_data.pdf_file:
            try:
                public_data.pdf_file.delete(save=False)
            except Exception:
                pass

        # Сохраняем новый файл
        public_data.pdf_file = uploaded_pdf
        # public_data.save() ниже

    elif remove_pdf_flag:
        # Удаляем текущий файл и обнулим поле
        if public_data.pdf_file:
            try:
                public_data.pdf_file.delete(save=False)
            except Exception:
                pass
            public_data.pdf_file = None

    # Сохраняем public_data
    public_data.save()

    # Формируем ответ (включая ссылку на pdf если есть)
    pdf_url = None
    try:
        if public_data.pdf_file and hasattr(public_data.pdf_file, "url"):
            pdf_url = public_data.pdf_file.url
    except Exception:
        pdf_url = None

    return JsonResponse({
        "success": True,
        "lesson": {
            "id": str(lesson_obj.id),
            "name": lesson_obj.name,
            "is_public": lesson_obj.is_public,
            "icon": public_data.icon,
            "level": public_data.level,
            "lexical_topics": public_data.lexical_topics,
            "grammar_topics": public_data.grammar_topics,
            "extra_topics": public_data.extra_topics,
            "meta_description": public_data.meta_description,
            "keywords": public_data.keywords,
            "pdf_url": pdf_url,
        }
    })




@login_required
def give_present(request):
    """
    Выдаёт подарок пользователю:
      - если тариф FREE -> активируем Премиум на 7 дней и шлём письмо (present_type="Подписка")
      - иначе -> начисляем +500 extra_tokens и шлём письмо (present_type="Токены")

    Возвращает JsonResponse с итогом.
    """
    user = request.user

    try:
        from users.views import send_gift_congrat_email
        with transaction.atomic():
            # Получаем тариф пользователя (если нет, считаем что free — но лучше create при регистрации)
            try:
                user_tariff = UserTariff.objects.select_for_update().get(user=user)
            except UserTariff.DoesNotExist:
                # Если записи нет — считаем бесплатным
                user_tariff = None

            if (user_tariff is None) or (user_tariff.tariff_type == TariffType.FREE):
                # Бесплатный — выдаём премиум на 7 дней
                period_start = timezone.now()
                period_end = period_start + timedelta(days=7)

                # Вызов функции активации тарифа.
                # Передаём duration в днях для совместимости; также указываем период явно.
                activate_user_tariff(
                    user=user,
                    tariff_type=TariffType.PREMIUM,
                    duration="MONTH",
                    amount_paid=0,
                    full_price=0,
                    period_start=period_start,
                    period_end=period_end,
                )

                # Отправляем письмо-поздравление
                try:
                    send_gift_congrat_email(user, present_type="Подписка")
                except Exception:
                    # не критично: логировать, но не ломать основной поток
                    pass

                return JsonResponse({
                    "status": "ok",
                    "present": "subscription",
                    "tariff": str(TariffType.PREMIUM),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                })

            else:
                # Не бесплатный — начисляем 500 дополнительных токенов
                tb, _ = UserTokenBalance.objects.select_for_update().get_or_create(user=user, defaults={
                    "tariff_tokens": 0,
                    "extra_tokens": 0,
                })
                tb.extra_tokens = (tb.extra_tokens or 0) + 500
                tb.save(update_fields=["extra_tokens", "updated_at"])

                # Отправляем письмо-поздравление
                try:
                    send_gift_congrat_email(user, present_type="Токены")
                except Exception:
                    pass

                return JsonResponse({
                    "status": "ok",
                    "present": "tokens",
                    "added_extra_tokens": 500,
                    "total_extra_tokens": tb.extra_tokens,
                    "total_tokens": tb.tokens,
                })

    except Exception as e:
        # В продакшне логируйте исключение через logger.exception
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
def onboarding(request):
    try:
        # Создаём/получаем запись онбординга для пользователя
        ob, _ = UserOnboarding.objects.get_or_create(user=request.user)

        # 🚫 Если уже завершён — не пускаем
        if ob.current_step == "done":
            return redirect("home")  # или другая страница, например "dashboard"

        # Проверка тарифа с обработкой исключений
        try:
            user_tariff = request.user.tariff  # OneToOneField -> UserTariff
            is_paid = user_tariff.tariff_type != TariffType.FREE
        except UserTariff.DoesNotExist:
            is_paid = False
        except Exception as e:
            # Логируем ошибку, но продолжаем работу
            logger.error(f"Error checking tariff for user {request.user.id}: {str(e)}")
            is_paid = False

        # Проверка токенов с обработкой исключений
        try:
            token_balance = request.user.token_balance  # OneToOneField -> UserTokenBalance
            low_tokens = token_balance.tokens < 50
        except UserTokenBalance.DoesNotExist:
            low_tokens = True  # если записи нет, считаем что токенов мало
        except Exception as e:
            # Логируем ошибку, но продолжаем работу
            logger.error(f"Error checking token balance for user {request.user.id}: {str(e)}")
            low_tokens = True

        # Контекст
        context = {
            "current_step": ob.current_step,  # str | None
            "generation_id": ob.generation_id,  # str | None
            "lesson_id": ob.lesson_id,  # str | None
            "is_paid": is_paid,
            "low_tokens": low_tokens,  # 🚀 добавили сюда
            # …и сразу одним JSON для удобства JS:
            "onboarding_json": json.dumps({
                "current_step": ob.current_step,
                "generation_id": ob.generation_id,
                "lesson_id": ob.lesson_id,
                "is_paid": is_paid,
                "low_tokens": low_tokens,
            }, cls=DjangoJSONEncoder),
        }

        return render(request, "home/onboarding.html", context)

    except Exception as e:
        # Логируем критическую ошибку
        logger.error(
            f"Critical error in onboarding view for user {request.user.id if request.user.is_authenticated else 'anonymous'}: {str(e)}")

        # Перенаправляем на домашнюю страницу с сообщением об ошибке
        messages.error(request, "Произошла ошибка при загрузке страницы. Пожалуйста, попробуйте позже.")
        return redirect("home")



@login_required
@require_POST
def start_generate_lesson(request):
    """
    Принимает JSON { topic: str, considerations?: str, course_id?: str }
    Создаёт запись LessonGenerationStatus и ставит задачу в очередь.
    Возвращает { generation_id, task_id } (202 Accepted).
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    topic = (payload.get("topic") or "").strip()
    considerations = payload.get("considerations")
    course_id = payload.get("course_id")

    if not topic or not request.user.is_authenticated:
        return HttpResponseBadRequest(json.dumps({"error": "topic_required"}), content_type="application/json")

    if request.user and request.user.is_authenticated:
        try:
            if hasattr(request.user, 'metrics'):
                request.user.metrics.lessons_generated_counter += 1
                request.user.metrics.save(update_fields=["lessons_generated_counter"])
        except Exception as e:
            # Логируем или просто пропускаем
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to increment tasks_generated_counter for user {request.user.id}: {e}")

    generation_id = payload.get("generation_id") or str(uuid.uuid4())

    # Если передан course_id — можно проверить его существование (не обязательно)
    if course_id:
        try:
            course_obj = Course.objects.filter(id=course_id, user=request.user).first()
            if not course_obj:
                return HttpResponseForbidden("У вас нет доступа к этому курсу")
        except Exception:
            course_id = None

    # Создаём начальную запись прогресса (если уже есть — не перезаписываем)
    status_obj, created = LessonGenerationStatus.objects.get_or_create(
        generation_id=generation_id,
        defaults={
            "user": request.user,
            "status": "pending",
            "total_tasks": 0,
            "completed_tasks": 0,
            "percent": 0.0,
        },
    )

    # Запускаем celery-задачу
    try:
        task = generate_lesson_task.delay(request.user.id, topic, generation_id=generation_id, course_id=course_id)
    except Exception as e:
        logger.exception("Failed to enqueue generate_lesson_task: %s", e)
        return HttpResponseServerError(json.dumps({"error": "enqueue_failed"}), content_type="application/json")

    return JsonResponse(
        {"generation_id": generation_id, "task_id": getattr(task, "id", None)},
        status=202,
    )


@login_required
def get_generation_status(request, generation_id: str):
    """
    Простой endpoint для чтения статуса по generation_id.
    Возвращает json: { generation_id, status, percent, total_tasks, completed_tasks, lesson_id? }
    """
    stat = LessonGenerationStatus.objects.filter(generation_id=generation_id, user=request.user).first()
    if not stat:
        return JsonResponse({"error": "not_found"}, status=404)

    return JsonResponse({
        "generation_id": stat.generation_id,
        "status": stat.status,
        "percent": float(stat.percent),
        "total_tasks": stat.total_tasks,
        "completed_tasks": stat.completed_tasks,
        "lesson_id": str(stat.lesson.id) if stat.lesson else None,
    })


ALLOWED_TASK_TYPES = {
    "WordList",
    "Note",
    "Article",
    "MatchUpTheWords",
    "Test",
    "TrueOrFalse",
    "SortIntoColumns",
    "LabelImages",
    "MakeASentence",
    "Unscramble",
}

def generate_lesson(user, lesson_topic: str, generation_id: Optional[str] = None, course_id: Optional[str] = None) -> float:
    """
    Создаёт (или использует существующий) Course, создаёт Lesson и генерирует секции и задания.
    Если передан course_id — пытаемся использовать соответствующий курс (только если он принадлежит user).
    Возвращает процент успешно созданных заданий (0..100).
    """
    generation_id = generation_id or str(uuid.uuid4())

    status_obj, _ = LessonGenerationStatus.objects.get_or_create(
        generation_id=generation_id,
        defaults={"user": user, "status": "pending", "percent": 0.0},
    )

    status_obj.mark_running()

    # Определяем course: если передан course_id — пытаемся взять его, иначе создаём/берём My Course
    with transaction.atomic():
        course_obj = None
        if course_id:
            try:
                course_candidate = Course.objects.filter(id=course_id).first()
                # используем только если курс найден и принадлежит пользователю
                if course_candidate and course_candidate.user_id == getattr(user, "id", None):
                    course_obj = course_candidate
                else:
                    # если курс найден, но не наш — не используем чужой, создаём новый
                    course_obj = None
            except Exception:
                course_obj = None

        if not course_obj:
            course_obj, _ = Course.objects.get_or_create(user=user, name="My Course")
            create_default_autogeneration_prefs(course_obj)

        # Создаём урок (auto_context = [])
        lesson_obj = Lesson.objects.create(
            course=course_obj,
            name="My Lesson",
            context={},
            is_public=False,
        )

        status_obj.lesson = lesson_obj
        status_obj.save(update_fields=["lesson", "updated_at"])

    # Шаг 2: запрос к ИИ за структурой разделов
    initial_query = (
        f'Составь план разделов для урока английского языка на тему \"{lesson_topic}\". '
        'Доступные типы заданий: WordList, Note, Article, MatchUpTheWords, Test, TrueOrFalse, SortIntoColumns, LabelImages, MakeASentence, Unscramble. '
        'JSON [{section_name: str, task_types: [str]}].'
    )

    try:
        sections_data = generate_handler(user=user, query=initial_query, desired_structure="JSON", model_type="premium")
    except Exception as e:
        logger.exception("generate_handler (sections) failed: %s", e)
        status_obj.mark_failed()
        return 0.0

    if not isinstance(sections_data, (list, tuple)):
        try:
            sections_data = json.loads(sections_data)
        except Exception:
            logger.error("Sections data is not JSON/list: %s", sections_data)
            status_obj.mark_failed()
            return 0.0

    total_tasks = 0
    completed_tasks = 0

    for sec in sections_data:
        task_types = sec.get("task_types", []) if isinstance(sec, dict) else []
        for t in task_types:
            if t in ALLOWED_TASK_TYPES:
                total_tasks += 1

    status_obj.total_tasks = total_tasks
    status_obj.save(update_fields=["total_tasks", "updated_at"])

    auto_context = ["Тема урока: " + lesson_topic]
    auto_context_str = f"Тема урока: {lesson_topic}"

    # Создаём секции и задания
    for sec in sections_data:
        if not isinstance(sec, dict):
            continue
        section_name = sec.get("section_name") or "Section"
        task_types = [t for t in sec.get("task_types", []) if t in ALLOWED_TASK_TYPES]

        # создаём learning секцию
        sec_obj = Section.objects.create(lesson=lesson_obj, name=section_name, type="learning")

        for task_type in sec.get("task_types", []):
            if task_type not in ALLOWED_TASK_TYPES:
                logger.warning("Skipping unknown task type: %s", task_type)
                continue

            params = {"task_type": task_type, "user_query": auto_context_str}
            try:
                base_query, desired_structure = build_base_query(params)
                enhanced_query = auto_context_str + enhance_query_with_params(base_query, params)

                try:
                    item_data = generate_handler(user=user, query=enhanced_query, desired_structure=desired_structure, model_type="premium")
                except Exception as e:
                    logger.exception("generate_handler for task %s failed: %s", task_type, e)
                    continue

                if isinstance(item_data, str):
                    try:
                        item_data = json.loads(item_data)
                    except Exception:
                        logger.warning("Item data for %s is not JSON, skipping", task_type)
                        continue

                if not isinstance(item_data, dict):
                    logger.warning("Item data for %s is not dict, skipping", task_type)
                    continue

                filtered_item_data = call_form_function(task_type, user, item_data)
                if filtered_item_data is None:
                    logger.info("Filtered data is None for %s, skipping", task_type)
                    continue

                auto_context = update_auto_context(auto_context, task_type, filtered_item_data)
                if auto_context:
                    joined = "\n".join(auto_context)
                    auto_context_str = (
                        "Ты - методист урока английского языка. Мы уже разработали несколько заданий урока:\n"
                        f"{joined}\n\n"
                        "Ты должен разработать задание в дополнение к уроку.\n"
                    )
                else:
                    auto_context_str = ""

                try:
                    task_instance = create_task_instance(user, task_type, filtered_item_data, sec_obj)
                except Exception as e:
                    print(e)
                    logger.exception("Failed to create task instance for %s: %s", task_type, e)
                    continue

                completed_tasks += 1
                status_obj.update_progress(completed_tasks, total_tasks)

            except Exception as e:
                print(e)
                logger.exception("Unhandled exception during generation of task %s: %s", task_type, e)
                continue

    status_obj.update_progress(completed_tasks, total_tasks)
    status_obj.mark_finished()

    return float(status_obj.percent)



@login_required
@require_POST
def onboarding_update(request):
    """
    Ожидает JSON: { "step": "<step_key>", optional: "topic", "role", "generation_id", "lesson_id" }
    Обновляет или создаёт запись UserOnboarding для текущего пользователя.
    Если step == "generation_result", ищет последнюю запись LessonGenerationStatus и возвращает ссылки.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    step = payload.get("step")
    print(payload)
    if not step or step not in dict(UserOnboarding.STEP_CHOICES):
        return JsonResponse({"error": "invalid or missing step"}, status=400)

    obj, _ = UserOnboarding.objects.get_or_create(user=request.user)

    # 🔒 Если статус уже "done", запрещаем изменения
    if obj.current_step == "done":
        return JsonResponse({
            "status": "locked",
            "step": obj.current_step,
            "lesson_id": obj.lesson_id or None,
        }, status=403)

    obj.current_step = step

    if "generation_id" in payload:
        obj.generation_id = payload.get("generation_id") or None
    if "lesson_id" in payload:
        obj.lesson_id = payload.get("lesson_id") or None

    # Обновление роли
    if "role" in payload:
        user = request.user
        user.teaching_role = payload["role"]
        user.save()

    obj.save()

    lesson_url = None
    pdf_url = None

    # если шаг generation_result → редиректим на последний сгенерированный урок
    if step == "generation_result":
        last_gen = (
            LessonGenerationStatus.objects
            .filter(user=request.user, lesson__isnull=False)
            .order_by("-created_at")
            .first()
        )
        if last_gen and last_gen.lesson:
            obj.lesson_id = last_gen.lesson.id or None
            obj.save(update_fields=["lesson_id"])
            lesson_url = reverse("lesson_page", args=[last_gen.lesson.id])
            pdf_url = reverse("download_pdf", args=[last_gen.lesson.id])

    if step == "done":
        give_present(request)

    return JsonResponse({
        "status": "ok",
        "step": obj.current_step,
        "lesson_id": obj.lesson_id or None,
        "lesson_url": lesson_url,
        "pdf_url": pdf_url,
    })



def public_lessons(request):
    """
    Собираем публичные уроки и передаём в шаблон в формате,
    удобном для шаблонизации.
    """
    try:
        qs = (
            Lesson.objects.filter(is_public=True)
            .select_related('public_data', 'course')
            .order_by('-created_at')
        )

        LEVEL_DISPLAY_MAP = {
            'A1': 'Beginner',
            'A2': 'Elementary',
            'B1': 'Intermediate',
            'B2': 'Upper-Intermediate',
            'C1': 'Advanced',
        }

        # Получаем email пользователя
        user_email = request.user.email if request.user.is_authenticated else None
        is_subscribed = False

        # Проверяем подписку
        if user_email:
            try:
                subscription = PublicLessonsEmails.objects.get(email=user_email)
                is_subscribed = subscription.allow_emails
            except ObjectDoesNotExist:
                pass

        lessons = []
        for lesson in qs:
            pd = getattr(lesson, 'public_data', None)

            # Определяем целевой url страницы урока
            if pd and pd.link_name:
                try:
                    view_url = reverse('public_lesson_preview', kwargs={'lesson_id': lesson.id})
                except Exception:
                    view_url = reverse('public_lesson_preview_by_id', kwargs={'pk': lesson.id})
            else:
                view_url = reverse('public_lesson_preview_by_id', kwargs={'pk': lesson.id})

            # raw icon value (строка — либо имя класса иконки, либо url)
            icon_val = (pd.icon if pd else '') or ''

            # уровень и человекочитаемое представление уровня
            level = (pd.level if pd else 'A1')
            try:
                level_display = pd.get_level_display() if pd else LEVEL_DISPLAY_MAP.get(level, level)
            except Exception:
                level_display = LEVEL_DISPLAY_MAP.get(level, level)

            # meta description и pdf (если есть)
            meta_description = (pd.meta_description if pd else '') or ''
            pdf_file = pd.pdf_file if (pd and getattr(pd, 'pdf_file', None)) else None

            lessons.append({
                'name': lesson.name,                      # не обязательно, но обычно полезно
                'url': view_url,                          # не обязательно, но удобно
                'icon': icon_val,
                'level': level,
                'get_level_display': level_display,
                'meta_description': meta_description,
                'pdf_file': pdf_file,
                'id': str(lesson.id),
            })

        # SEO
        page_meta_description = (
            "Бесплатные и готовые планы уроков и рабочие листы по английскому "
            "для репетиторов — подбор по теме и уровню."
        )
        page_keywords = (
            "план урока по английскому, рабочие листы по английскому, "
            "уроки английского, материалы для репетиторов"
        )

        return render(
            request,
            'builder/public/public_lessons_landing.html',
            {
                'lessons': lessons,
                'page_meta_description': page_meta_description,
                'page_keywords': page_keywords,
                'page_title': 'LinguaGlow — рабочие листы и планы уроков по английскому',
                'email': request.user.email if request.user.is_authenticated else "",
                'is_subscribed': is_subscribed,  # Добавляем флаг подписки
                'is_authenticated': request.user.is_authenticated,
            }
        )

    except Exception as e:
        return render(
            request,
            'builder/public/public_lessons_landing.html',
            {
                'lessons': [],
                'page_meta_description': "",
                'page_keywords': "",
                'page_title': 'LinguaGlow — рабочие листы и планы уроков по английскому'
            }
        )

def public_lesson_preview(request, lesson_id):
    try:
        lesson_obj = (
            Lesson.objects.select_related("course", "public_data")
            .get(id=lesson_id, is_public=True)
        )

        course_obj = lesson_obj.course

        is_authenticated = request.user.is_authenticated

        if is_authenticated:
            classrooms = Classroom.objects.filter(Q(teachers=request.user) | Q(students=request.user)).distinct()
        else:
            classrooms = ""

        sections = get_sorted_sections(lesson_obj)
        section_ids = [section.id for section in sections]

        # Сохраняем порядок секций
        section_ordering = Case(
            *[When(section_id=pk, then=pos) for pos, pk in enumerate(section_ids)],
            output_field=IntegerField()
        )

        tasks = (
            BaseTask.objects.filter(section__in=section_ids)
            .select_related("content_type")
            .annotate(section_order=section_ordering)
            .order_by("section_order", "order")
        )

        context = {
            "lesson": lesson_obj,
            'section_list': sections,
            "user_id": request.user.id if is_authenticated else "",
            'course_id': course_obj.id,
            "is_authenticated": is_authenticated,
            "tasks": tasks,
            "classrooms": classrooms
        }
        return render(request, "builder/public/public_preview.html", context)

    except Lesson.DoesNotExist:
        raise Http404("Урок не найден")

    except Exception as e:
        print("Ошибка в public_lesson_preview:", e)
        traceback.print_exc()
        return render(request, "500.html", {"error": str(e)}, status=500)

@ratelimit(key='ip', rate='20/h', block=True)
def download_public_pdf(request, lesson_id):
    try:
        lesson = Lesson.objects.select_related("public_data").get(id=lesson_id, is_public=True)

        if not lesson.public_data or not lesson.public_data.pdf_file:
            raise Http404("Файл не найден")

        pdf_path = lesson.public_data.pdf_file.path
        if not os.path.exists(pdf_path):
            raise Http404("Файл не найден")

        filename = os.path.basename(pdf_path)
        response = FileResponse(open(pdf_path, "rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        if request.user and request.user.is_authenticated:
            try:
                if hasattr(request.user, 'metrics'):
                    request.user.metrics.pdf_downloaded_counter += 1
                    request.user.metrics.save(update_fields=["pdf_downloaded_counter"])
            except Exception as e:
                # Логируем или просто пропускаем
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to increment tasks_generated_counter for user {request.user.id}: {e}")

        return response

    except Lesson.DoesNotExist:
        raise Http404("Урок не найден")

@require_POST
@login_required
def pdf_downloaded(request):
    try:
        metrics, _ = UserMetrics.objects.get_or_create(user=request.user)
        metrics.update_activity()
        metrics.pdf_downloaded_counter += 1
        metrics.save(update_fields=["pdf_downloaded_counter", "last_activity_at", "first_activity_at"])
        return JsonResponse({"status": "ok", "pdf_downloaded_counter": metrics.pdf_downloaded_counter})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@require_POST
@ratelimit(key='ip', rate='2/d', block=True)
def subscribe_email(request):
    try:
        email = request.POST.get('email').strip().lower()  # Приводим к нижнему регистру и убираем пробелы

        if not email:
            return JsonResponse({
                'success': False,
                'error': 'Email не указан'
            }, status=400)

        # Валидируем формат email
        validate_email(email)

        # Проверяем существование email в базе
        if PublicLessonsEmails.objects.filter(email__iexact=email).exists():
            return JsonResponse({
                'success': False,
                'error': 'Email уже существует в базе'
            }, status=409)

        # Создаем новую запись
        subscription = PublicLessonsEmails.objects.create(
            email=email,
            allow_emails=True
        )

        return JsonResponse({
            'success': True,
            'message': 'Email успешно добавлен'
        }, status=201)

    except ValidationError:
        return JsonResponse({
            'success': False,
            'error': 'Неверный формат email'
        }, status=400)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Произошла ошибка: {str(e)}'
        }, status=500)

@login_required
@require_POST
def link_telegram(request):
    # создаём уникальный токен
    token = TelegramAuthToken.objects.create(
        user=request.user,
        token=uuid.uuid4().hex
    )

    bot_username = "linguaglow_bot"  # замени на реальное имя бота
    url = f"https://t.me/{bot_username}?start={token.token}"

    return JsonResponse({"url": url})




@login_required
def invitation_guide(request):
    user = request.user

    # проверяем, что пользователь — teacher
    if getattr(user, "role", None) != "teacher":
        return redirect("landing")

    # ищем первый класс, где user учитель
    classroom = user.classrooms_as_teacher.first()

    # если класса нет — создаём
    if not classroom:
        classroom = Classroom.objects.create(name="My Class")
        classroom.teachers.add(user)

    # генерируем ссылку-приглашение
    classroom_link = request.build_absolute_uri(
        reverse("accept_invitation", args=[classroom.invitation_code])
    )

    return render(
        request,
        "articles/invitation-guide.html",
        {
            "is_authenticated": True,
            "classroom_link": classroom_link,
        }
    )

def ensure_user_lesson(user):
    """
    Возвращает (course_id, lesson_id) для пользователя-учителя:
    - если есть урок -> (course.id, lesson.id)
    - если нет урока, но есть курс -> создаёт урок -> (course.id, lesson.id)
    - если нет курса -> создаёт курс + урок -> (course.id, lesson.id)
    """
    if getattr(user, "role", None) != "teacher":
        return None, None

    try:
        # 1) есть ли урок?
        lesson = Lesson.objects.filter(course__user=user).first()
        if lesson:
            return lesson.course.id, lesson.id

        # 2) есть курс?
        course = Course.objects.filter(user=user).first()
        if course:
            with transaction.atomic():
                lesson = Lesson.objects.create(
                    course=course,
                    name="Lesson 1",
                    is_public=False,
                    context={}
                )

                if user.is_staff:
                    LessonPublicData.objects.create(lesson=lesson)

                Section.objects.create(
                    lesson=lesson,
                    name="Let's begin! 😉",
                    type="learning"
                )
            return course.id, lesson.id

        # 3) нет ни курса, ни урока
        with transaction.atomic():
            new_course = Course.objects.create(
                name="New Course",
                description="",
                student_level="A1",  # дефолтное значение
                user=user
            )
            create_default_autogeneration_prefs(new_course)

            lesson = Lesson.objects.create(
                course=new_course,
                name="Lesson 1",
                is_public=False,
                context={}
            )

            Section.objects.create(
                lesson=lesson,
                name="Let's begin! 😉",
                type="learning"
            )
        return new_course.id, lesson.id

    except Exception:
        logger.exception("ensure_user_lesson failed for user %s", user.pk)
        return None, None

@login_required
def course_guide(request):
    user = request.user

    if getattr(user, "role", None) != "teacher":
        return redirect("landing")

    course_id, lesson_id = ensure_user_lesson(user)

    return render(
        request,
        "articles/course-guide.html",
        {
            "is_authenticated": True,
            "course_id": course_id,
            "lesson_id": lesson_id,
        }
    )

