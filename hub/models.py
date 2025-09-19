import hashlib
import json
import random
import string

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import JSONField
import uuid
import bleach
from datetime import timedelta, timezone, datetime

from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.text import slugify
from django.utils.timezone import now
from django_cron import CronJobBase, Schedule
from django.db import models
from django.conf import settings

from users.models import CustomUser


class CourseManager(models.Manager):
    def for_user(self, user):
        return self.filter(models.Q(user=user) | models.Q(lessons__sections__tasks__assigned_users=user)).distinct()

class Course(models.Model):
    STUDENT_LEVEL_CHOICES = (
        ("starter", "Starter"),
        ("elementary", "Elementary"),
        ("pre_intermediate", "Pre-Intermediate"),
        ("intermediate", "Intermediate"),
        ("upper_intermediate", "Upper-Intermediate"),
        ("advanced", "Advanced"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)  # Название курса
    description = models.TextField(blank=True, null=True)  # Описание курса
    student_level = models.CharField(max_length=20, choices=STUDENT_LEVEL_CHOICES, default="starter")  # Уровень ученика
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses")  # Автор курса
    created_at = models.DateTimeField(auto_now_add=True)  # Дата создания курса
    updated_at = models.DateTimeField(auto_now=True)  # Дата последнего обновления

    objects = CourseManager()

    def __str__(self):
        return self.name

class Lesson(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    name = models.CharField(max_length=255)

    is_public = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    context = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} (Course: {self.course.name})"

PUBLIC_LEVEL_CHOICES = [
    ('A1', 'Beginner'),
    ('A2', 'Elementary'),
    ('B1', 'Intermediate'),
    ('B2', 'Upper-Intermediate'),
    ('C1', 'Advanced'),
]

class LessonPublicData(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='public_data')

    lexical_topics = models.TextField(blank=True, null=True)
    grammar_topics = models.TextField(blank=True, null=True)
    extra_topics = models.TextField(blank=True, null=True)

    meta_description = models.CharField(max_length=160, blank=True, null=True)
    keywords = models.CharField(max_length=255, blank=True, null=True)

    icon = models.CharField(
        max_length=50,  # Увеличен размер для текстового описания
        blank=True,
        null=True,
        verbose_name='Иконка'
    )

    level = models.CharField(
        max_length=2,
        choices=PUBLIC_LEVEL_CHOICES,
        default='A1',
        verbose_name='Уровень'
    )

    link_name = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Ссылка"
    )

    pdf_file = models.FileField(
        upload_to='lesson_pdfs/',  # папка для загрузки
        blank=True,
        null=True,
        verbose_name='PDF файл'
    )

    def save(self, *args, **kwargs):
        if not self.link_name and self.lesson:
            self.link_name = slugify(self.lesson.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Public data for: {self.lesson.name}"

class Section(models.Model):
    TYPE_CHOICES = [
        ("completion", "Закрепление"),
        ("learning", "Обучающий"),
        ("hometask", "Домашнее задание"),
        ("revision", "Повторение"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='learning')
    order = models.PositiveIntegerField(default=0, help_text="Порядок секции внутри урока")

    class Meta:
        ordering = ["order"]  # секции всегда сортируются по order

    def save(self, *args, **kwargs):
        if self._state.adding and self.order == 0:
            # если новая секция и order не задан → поставить в конец
            last_order = (
                Section.objects.filter(lesson=self.lesson)
                .aggregate(models.Max("order"))["order__max"]
            )
            self.order = (last_order or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (Lesson: {self.lesson.name}, Type: {self.get_type_display()})"


class MediaFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='media_files'
    )
    file = models.FileField(upload_to='uploads', max_length=1000)
    size = models.PositiveIntegerField(default=0)  # в байтах
    hash = models.CharField(max_length=64, unique=True, blank=True)  # SHA-256 = 64 символа
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        file_url = str(self.file)

        if file_url.startswith('https://') or file_url.startswith('http://'):
            # Внешняя ссылка — пропускаем хэширование и определение размера
            self.file = ''
            self.hash = ''
            self.size = 0
        else:
            if self.file and not self.hash:
                self.file.seek(0)
                self.size = self.file.size
                self.hash = self.calculate_hash()
                self.file.seek(0)

        super().save(*args, **kwargs)

    def calculate_hash(self):
        """Вычисляет SHA-256 хеш файла."""
        sha256 = hashlib.sha256()
        self.file.seek(0)  # Перемотать начало файла
        for chunk in self.file.chunks():
            sha256.update(chunk)
        self.file.seek(0)  # Вернуть указатель в начало
        return sha256.hexdigest()

class CoursePdf(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='pdfs')
    media = models.ForeignKey(MediaFile, on_delete=models.CASCADE, related_name='course_pdfs')
    title = models.CharField(max_length=255, help_text="Отображаемое название PDF-документа")
    url = models.URLField(max_length=1000, blank=True, help_text="Если media.file — внешняя ссылка, можно задавать напрямую")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "PDF документа курса"
        verbose_name_plural = "PDF документы курса"

    def save(self, *args, **kwargs):
        if not self.url and self.media and self.media.file:
            try:
                self.url = self.media.file.url
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.course.name})"

class BaseTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, related_name='%(class)s_tasks')
    order = models.PositiveIntegerField()  # Порядок задания в секции
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    size = models.PositiveIntegerField(default=1)  # Размер задания
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Дата последнего обновления

    media = models.ManyToManyField(MediaFile, blank=True)

    def __str__(self):
        return f"Base Task {self.id}"


# Список слов
class WordList(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Список слов")
    words = models.JSONField()  # Список слов в формате JSON

    def __str__(self):
        return f"Word List: {self.title}"

# Соотнести слово с переводом
class MatchUpTheWords(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Соотнесите слова с переводами")
    pairs = models.JSONField()  # Пары слов в формате JSON

    def __str__(self):
        return f"Match Up The Words: {self.id}"

# Эссе
class Essay(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.TextField()
    conditions = models.JSONField(null=True)

    def __str__(self):
        return f"Essay: {self.title}"

# Заметка
class Note(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Заметка")
    content = models.TextField()

    def __str__(self):
        return f"Note: {self.content[:50]}..."


# Картинка
class Image(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Изображение")
    image_url = models.URLField(max_length=1000)

    def __str__(self):
        return f"Image: {self.title}"

# Распределить по колонкам
class SortIntoColumns(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Распределите по колонкам")
    columns = models.JSONField()  # Колонки и их элементы в формате JSON

    def __str__(self):
        return f"Sort Into Columns: {self.id}"

# Составить предложение в правильном порядке
class MakeASentence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Составьте предложения")
    sentences = models.JSONField()

    def __str__(self):
        return f"Make A Sentence: {self.id}"

# Составить слово
class Unscramble(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Составьте слова из букв")
    words = models.JSONField()

    def __str__(self):
        return f"Unscramble: {self.words}"

# Заполнить пропуски
class FillInTheBlanks(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Заполните пропуски")
    text = models.TextField()

    DISPLAY_FORMAT_CHOICES = [
        ('withList', 'With list'),
        ('withoutList', 'Without list'),
    ]

    display_format = models.CharField(
        max_length=20,
        choices=DISPLAY_FORMAT_CHOICES,
        default='withList',  # Значение по умолчанию
    )

    def __str__(self):
        return f"Fill In The Blanks: {self.id}"

# Диалог
class Dialogue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lines = models.JSONField()  # Реплики диалога в формате JSON

    def __str__(self):
        return f"Dialogue: {self.id}"

# Статья
class Article(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Статья")
    content = models.TextField()

    def __str__(self):
        return f"Article: {self.title}"

# Аудио
class Audio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Прослушай аудио")
    audio_url = models.URLField()
    transcript = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Audio: {self.audio_url}"

# Тест
class Test(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Тест")
    questions = models.JSONField()  # Вопросы и варианты ответов в формате JSON

    def __str__(self):
        return f"Test: {self.id}"

# Правда или ложь
class TrueOrFalse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Правда или ложь")
    statements = models.JSONField()  # Утверждения и их правильность в формате JSON

    def __str__(self):
        return f"True Or False: {self.id}"

class LabelImages(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Подпишите картинку")
    images = models.JSONField()  # [{ "url": "...", "label": "..." }, ...]

    def __str__(self):
        return f"Label Images: {self.title} ({self.id})"

# Quizlet и WordWall
class EmbeddedTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Выполните интерактивное задание")
    embed_code = models.TextField()  # Здесь будет храниться HTML-код iframe

    def save(self, *args, **kwargs):
        # Разрешаем только iframe и его атрибуты
        allowed_tags = ['iframe']
        allowed_attrs = {
            'iframe': ['src', 'width', 'height', 'frameborder', 'allow', 'allowfullscreen', 'style', 'class']
        }

        # Очищаем HTML-код, сохраняя только разрешенные теги и атрибуты
        self.embed_code = bleach.clean(
            self.embed_code,
            tags=allowed_tags,
            attributes=allowed_attrs,
            strip=True  # Удаляем все неразрешенные теги и атрибуты
        )

        # Вызов стандартного метода save
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

# PDF
class Pdf(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Документ PDF")
    pdf_url = models.URLField(max_length=1000, default=None)

    def __str__(self):
        return f"PDF: {self.title}"




class ClassroomManager(models.Manager):
    def for_user(self, user):
        return self.filter(models.Q(students=user) | models.Q(teachers=user)).distinct()

def generate_unique_invitation_code():
    """Генерирует уникальный 7-символьный код для класса."""
    from .models import Classroom  # импорт здесь, чтобы избежать циклического импорта
    while True:
        code = str(uuid.uuid4())[:7]
        if not Classroom.objects.filter(invitation_code=code).exists():
            return code

class Classroom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255, default="Class")

    # Учителя (только пользователи с ролью "teacher")
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="classrooms_as_teacher",
        limit_choices_to={"role": "teacher"},
        verbose_name="Учителя"
    )

    # Ученики (роль: student или teacher, но не учителя из списка teachers)
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="classrooms_as_student",
        limit_choices_to={"role__in": ["student", "teacher"]},
        verbose_name="Ученики"
    )

    # Текущий урок (активный)
    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name="classrooms")
    objects = ClassroomManager()

    invitation_code = models.CharField(
        max_length=7,
        unique=True,
        default=generate_unique_invitation_code,
        editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)  # Дата создания класса
    updated_at = models.DateTimeField(auto_now=True)  # Дата последнего обновления

    features = models.JSONField(default=dict)    # Запрет/разрешение копирования

    def clean(self):
        """Запрещаем добавление учителей в список учеников"""
        if set(self.teachers.all()) & set(self.students.all()):
            raise ValueError("Учителя не могут быть учениками в этом классе.")

    def __str__(self):
        return f"Classroom {self.id}"

class UserAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="user_answers")
    task = models.ForeignKey(BaseTask, on_delete=models.CASCADE, related_name="user_answers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_answers")
    answer_data = models.JSONField(default=list)  # Хранение массива ответов в формате JSON
    correct_answers = models.IntegerField(default=0)  # Количество правильных ответов
    incorrect_answers = models.IntegerField(default=0)  # Количество неправильных ответов
    max_score = models.IntegerField(default=10)  # Заглушка для максимального балла
    submitted_at = models.DateTimeField(auto_now_add=True)  # Время первого ответа
    updated_at = models.DateTimeField(auto_now=True)  # Время последнего ответа

    class Meta:
        unique_together = ('classroom', 'task', 'user')  # Один пользователь - одна запись на задание в классе

    def __str__(self):
        return f"UserAnswer(id={self.id}, user={self.user}, task={self.task})"

    @classmethod
    def delete_old_answers(cls):
        expiration_date = timezone.now() - timedelta(days=180)
        cls.objects.filter(updated_at__lt=expiration_date).delete()

class DeleteOldAnswersCronJob(CronJobBase):
    RUN_EVERY_MINS = 1440  # Запуск раз в день
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'app.delete_old_answers'

    def do(self):
        UserAnswer.delete_old_answers()



class UserAutogenerationPreferences(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='autogeneration_preferences')
    task_types_lexical = models.JSONField(default=dict)
    task_types_listening = models.JSONField(default=dict)
    task_types_reading = models.JSONField(default=dict)
    task_types_grammar = models.JSONField(default=dict)
    task_types_speaking = models.JSONField(default=dict)
    task_types_other = models.JSONField(default=dict)

#task_types_lexical = {"WordList": {"user_query": ""}, "Sort Into Columns": {"user_query": ""}, "Fill In The Blanks": {"user_query": ""}}
class Generation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    section_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="pending")  # pending / in_progress / done / failed
    tasks = models.JSONField(default=list)  # список task_id для Celery

class LessonGenerationStatus(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("finished", "Finished"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_generations")
    lesson = models.ForeignKey("Lesson", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    generation_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_tasks = models.PositiveIntegerField(default=0)
    completed_tasks = models.PositiveIntegerField(default=0)
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def update_progress(self, completed: int, total: int):
        self.completed_tasks = completed
        self.total_tasks = total
        self.percent = round((completed / total * 100) if total else 0.0, 2)
        self.save(update_fields=["completed_tasks", "total_tasks", "percent", "updated_at"])

    def mark_running(self):
        self.status = "running"
        self.save(update_fields=["status", "updated_at"])

    def mark_finished(self):
        self.status = "finished"
        self.percent = 100.0
        self.save(update_fields=["status", "percent", "updated_at"])

    def mark_failed(self):
        self.status = "failed"
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"Generation {self.generation_id or self.id} for {self.user} - {self.status}"

class UserContextLength(models.Model):
    CONTEXT_CHOICES = [
        (1000, '1000 символов'),
        (2000, '2000 символов'),
        (4000, '4000 символов'),
        (8000, '8000 символов'),
    ]

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='context_length')
    context_length = models.PositiveIntegerField(choices=CONTEXT_CHOICES, default=2000)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} — {self.context_length} символов"

class Homework(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Отправлено'),
        ('completed', 'На проверке'),
        ('resent', 'Исправить'),
        ('checked', 'Проверено'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    classroom = models.ForeignKey(
        'Classroom',
        on_delete=models.CASCADE,
        related_name='homeworks',
        verbose_name='Класс'
    )

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='homeworks',
        verbose_name='Ученик'
    )

    lesson = models.ForeignKey(
        'lesson',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='homeworks',
        verbose_name='Урок'
    )

    tasks = models.ManyToManyField(BaseTask, related_name='homeworks', blank=True, verbose_name='Задания')

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_homeworks',
        verbose_name='Назначено учителем'
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='sent',
        verbose_name='Статус'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата назначения')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    comment = models.TextField(blank=True, null=True, verbose_name='Комментарий учителя')

    def __str__(self):
        return f"HW for {self.student} ({self.classroom.name}) - {self.status}"


class SavedUnsplashImage(models.Model):
    query = models.CharField(max_length=100, db_index=True)
    url = models.URLField()
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('query', 'url')
        indexes = [
            models.Index(fields=['query']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.query} - {self.url}"




class SiteErrorLog(models.Model):
    error_message = models.TextField(help_text="Описание ошибки")
    function_name = models.CharField(max_length=255, help_text="Функция или метод, где произошла ошибка")
    created_at = models.DateTimeField(default=timezone.now, help_text="Время возникновения ошибки")

    def __str__(self):
        return f"{self.function_name} — {self.error_message[:50]}..."

    class Meta:
        verbose_name = "Ошибка сайта"
        verbose_name_plural = "Ошибки сайта"
        ordering = ['-created_at']

class GenerationStats(models.Model):
    TYPE_CHOICES = [
        ('images', 'Images'),
        ('audio', 'Audio'),
        ('text', 'Text'),
        ('tokens', 'Tokens'),
        ('functions', 'Functions'),
    ]

    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    successful_generations = models.PositiveIntegerField(default=0)
    unsuccessful_generations = models.PositiveIntegerField(default=0)
    error_text = models.TextField(default='', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"


class PublicLessonsEmails(models.Model):
    email = models.EmailField(
        unique=True,
        verbose_name='Email пользователя'
    )
    allow_emails = models.BooleanField(
        default=True,
        verbose_name='Разрешить рассылки'
    )

    class Meta:
        verbose_name = 'Email для рассылок'
        verbose_name_plural = 'Email-адреса для рассылок'

    def __str__(self):
        return self.email


