import json
import base64
import logging
import math
import re
import random
import secrets
import traceback
from django.shortcuts import get_object_or_404
from asgiref.sync import async_to_sync
from celery import shared_task, states, chain, group
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from edge_tts import Communicate
from exceptiongroup import catch
from pdf2image import convert_from_bytes
import pytesseract
from hub.models import Lesson
from .models import Section, UserAutogenerationPreferences, MediaFile, LessonGenerationStatus
from .ai_calls import generate_handler, has_min_tokens, take_tokens, add_successful_generation, search_images_api, extract_json_or_array_from_text
from users.models import CustomUser
from .utils import process_image_data, build_base_query, enhance_query_with_params, extract_lesson_context, \
    update_auto_context, markdown_to_html, shuffle_sentence, shuffle_word


def decode_and_extract_text_from_base64_pdf(base64_string):
    """Декодирует PDF из Base64 и извлекает текст через OCR."""
    print("decode_and_extract_text_from_base64_pdf: Начало декодирования PDF")
    if base64_string.startswith("data:application/pdf;base64,"):
        base64_string = base64_string.split("base64,")[1]
        print("decode_and_extract_text_from_base64_pdf: Удалён префикс data URI")

    try:
        pdf_data = base64.b64decode(base64_string)
        print(f"decode_and_extract_text_from_base64_pdf: PDF декодирован, длина данных {len(pdf_data)} байт")
    except Exception as e:
        print(f"decode_and_extract_text_from_base64_pdf: Ошибка декодирования base64: {e}")
        raise

    try:
        images = convert_from_bytes(pdf_data)
        print(f"decode_and_extract_text_from_base64_pdf: PDF конвертирован в {len(images)} изображений")
    except Exception as e:
        print(f"decode_and_extract_text_from_base64_pdf: Ошибка конвертации PDF в изображения: {e}")
        raise

    text_parts = []
    for page_num, image in enumerate(images, start=1):
        try:
            page_text = pytesseract.image_to_string(image, lang='eng+rus')
            print(f"decode_and_extract_text_from_base64_pdf: Текст извлечён с страницы {page_num}")
            text_parts.append(f"\n--- Page {page_num} ---\n{page_text.strip()}")
        except Exception as e:
            print(f"decode_and_extract_text_from_base64_pdf: Ошибка OCR на странице {page_num}: {e}")

    full_text = "\n".join(text_parts).strip()
    print("decode_and_extract_text_from_base64_pdf: Завершено извлечение текста из PDF")
    return full_text

TASK_TYPE_MODEL_PREFERENCE = {
    "WordList":        "basic",
    "Test":            "premium",
    "FillInTheBlanks": "premium",
    "MatchUpTheWords": "basic",
    "MakeASentence":   "basic",
    "Unscramble":      "basic",
    "TrueOrFalse":     "premium",
    "Transcript":      "premium",
    "Essay":           "basic",
    "Note":            "premium",
    "Article":         "premium",
    "SortIntoColumns": "basic",
    "LabelImages":     "basic"
}

@shared_task(bind=True, name="process_pdf_section_task")
def process_pdf_section_task(self, section_id, query, pdf_base64, user_id):
    from django.contrib.auth import get_user_model
    from .views import create_task_instance
    from hub.views import call_form_function
    User = get_user_model()

    def make_error(msg: str) -> dict:
        return {"status": "error", "error": msg}

    print(f"[process_pdf_section_task] Запуск задачи для section_id={section_id}, user_id={user_id}")

    # --- Проверка раздела
    try:
        section_obj = get_object_or_404(Section, id=section_id)
    except Exception as e:
        print(f"[process_pdf_section_task] Раздел не найден: {e}")
        return make_error("Section not found")

    if section_obj.lesson.course.user.id != user_id:
        print("[process_pdf_section_task] Доступ запрещён для пользователя")
        return make_error("Access denied")

    # --- Извлечение текста из PDF
    try:
        full_text = decode_and_extract_text_from_base64_pdf(pdf_base64)
    except Exception as e:
        print(f"[process_pdf_section_task] Ошибка при извлечении текста: {e}")
        return make_error(f"OCR error: {str(e)}")
    print("[DEBUG] TEXT: ", full_text[:100])
    # --- Подготовка system prompt
    system_prompt = (
        "SYSTEM PROMPT: Format the tasks content into JSON as structured objects. Task types must be from the list. WRITE FULL TASK CONTENT!\n"
        "For each task provide:\n"
        "- task_type: from the list: WordList, Note, FillInTheBlanks, MatchUpTheWords, Reading, Test, TrueOrFalse, MakeASentence, SortIntoColumns, Writing, ListeningMonologue, LabelImages, Unscramble, SpeakingQuestion, WritingQuestion, ComprehensionQuestion, Speaking, GrammarNote\n"
        "- instuctions\n"
        "- content\n"
        "- answers (if relevant)\n\n"
        "Return only JSON ARRAY: [{'task_type': str, 'instruction': str, 'content': str, 'answers': str}, ...]."
    )
    if query:
        system_prompt += f"\nAdditional instructions: {query}"
    system_prompt += " The text: \n\n"

    # --- Генерация заданий
    try:
        user = CustomUser.objects.get(id=user_id)
        generated_data = generate_handler(
            user=user,
            query=system_prompt + full_text,
            desired_structure="JSON [{'task_type': str, 'instruction': str, 'content': str, 'answers': str}]",
            model_type="premium"
        )
        print(f"[process_pdf_section_task] Данные от генератора: {generated_data}")
        if not generated_data:
            return make_error("Generation returned empty result")
    except Exception as e:
        print(f"[process_pdf_section_task] Ошибка генерации: {e}")
        return make_error(f"Generation error: {str(e)}")

    # --- Проверка формата JSON
    if not isinstance(generated_data, list):
        if isinstance(generated_data, str):
            try:
                parsed = json.loads(generated_data)
                if isinstance(parsed, list):
                    generated_data = parsed
                else:
                    return make_error("Parsed data is not a list")
            except json.JSONDecodeError as e:
                print(f"[process_pdf_section_task] Ошибка JSON decode: {e}")
                return make_error("Failed to decode JSON")
        else:
            return make_error("Invalid format from generator")

    # --- Обработка заданий
    results = []
    for idx, item in enumerate(generated_data, 1):
        try:
            task_type = item.get("task_type")
            print(f"[process_pdf_section_task] Обработка задания #{idx} ({task_type})")

            # Маппинг типов
            consider = ""
            if task_type in ["SpeakingQuestion", "ComprehensionQuestion", "Speaking", "GrammarNote"]:
                task_type_original = task_type
                task_type = "Note"
                if task_type_original != "GrammarNote":
                    consider = " SYSTEM PROMPT: Just rewrite the original task."
            elif task_type in ["WritingQuestion", "Writing", "Essay"]:
                task_type = "Essay"
            elif task_type == "Reading":
                task_type = "Article"
            elif task_type == "ListeningMonologue":
                task_type = "Audio"

            # Данные
            instruction = item.get("instruction") or ""
            content_part = item.get("content") or ""
            answers = item.get("answers") or ""

            if instruction:
                instruction = " SYSTEM_TITLE: " + instruction
            if content_part:
                content_part = " SYSTEM_CONTENT: " + content_part
            if answers:
                answers = " SYSTEM_ANSWERS: " + answers

            if task_type in ["MatchUpTheWords", "TrueOrFalse", "Test", "Unscramble",
                             "MakeASentence", "SortIntoColumns", "FillInTheBlanks"]:
                content = instruction + content_part + answers + consider
            else:
                content = instruction + content_part + consider

            if not task_type or not (instruction or content_part):
                print(f"[process_pdf_section_task] Пропуск #{idx} — нет типа или контента")
                continue

            if task_type not in TASK_TYPE_MODEL_PREFERENCE and task_type != "Audio":
                print(f"[process_pdf_section_task] Пропуск #{idx} — неподдерживаемый тип {task_type}")
                continue

            # --- Генерация task_core
            try:
                params = {
                    "lesson_id": section_obj.lesson.id,
                    "task_type": task_type,
                    "context_flag": False,
                    "emoji": False,
                    "user_query": content,
                    "is_copy": True
                }
                prepared_data = generate_task_core(user, params)
                if prepared_data:
                    payload = prepared_data.get("data")
                else:
                    print(f"[process_pdf_section_task] Пустые prepared_data для задания #{idx}")
                    continue
            except Exception as e:
                print(f"[process_pdf_section_task] Ошибка в generate_task_core для #{idx}: {e}")
                continue

            # --- Формирование данных
            try:
                task_data = call_form_function(task_type, user, payload=payload)
                if not task_data:
                    print(f"[process_pdf_section_task] Не удалось сформировать данные для #{idx}")
                    continue
            except Exception as e:
                print(f"[process_pdf_section_task] Ошибка в call_form_function для #{idx}: {e}")
                continue

            # --- Создание объекта
            try:
                task_obj = create_task_instance(user, task_type, task_data, section_obj)
                results.append({"task_id": task_obj.id, "task_type": task_type})
                print(f"[process_pdf_section_task] Задание #{idx} создано (id={task_obj.id})")
            except Exception as e:
                print(f"[process_pdf_section_task] Ошибка создания task_instance для #{idx}: {e}")
                continue

        except Exception as e:
            print(f"[process_pdf_section_task] Критическая ошибка обработки #{idx}: {e}")
            continue

    # --- Итог
    if not results:
        return make_error("No tasks were created from generated data")

    print("[process_pdf_section_task] Завершение задачи")
    return {"status": "ok", "result": results}







MAX_AUDIO_SIZE = 80 * 1024 * 1024

def clean_text(text):
    # Удаляем эмодзи
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # смайлики
        "\U0001F300-\U0001F5FF"  # символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # транспорт и карты
        "\U0001F1E0-\U0001F1FF"  # флаги
        "\U00002700-\U000027BF"  # различные символы
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)

    # Удаляем эмодзи из текста
    text = emoji_pattern.sub(r'', text)

    # Оставляем только допустимые символы:
    # - латинские буквы (строчные и заглавные)
    # - кириллица (строчная и заглавная)
    # - цифры
    # - пробелы
    # - основные знаки препинания
    # - дефис и кавычки
    text = re.sub(r'[^a-zA-Zа-яА-Я0-9\s.,!?:;\-\'"]+', '', text)

    # Удаляем лишние пробелы и возвращаем очищенный текст
    return re.sub(r'\s+', ' ', text).strip()

@shared_task(bind=True)
def generate_audio_task(self, user_id, text, voice='en-US-JennyNeural', rate='+0%', pitch='+0Hz'):
    """
    Celery задача для генерации аудио.
    Возвращает байты аудио в base64 или путь к файлу (в зависимости от реализации).
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.get(id=user_id)

    clean = clean_text(text)
    if len(clean) < 1 or len(clean) > 5000:
        self.update_state(state=states.FAILURE, meta={'exc_message': 'Недопустимая длина текста'})
        return

    cost = math.ceil(len(clean) / 100)

    # Проверки токенов
    if not has_min_tokens(user, min_tokens=-25):
        self.update_state(state=states.FAILURE, meta={'exc_message': 'Недостаточно токенов для генерации аудио'})
        return

    if not take_tokens(user, cost):
        self.update_state(state=states.FAILURE, meta={'exc_message': 'Не удалось списать токены'})
        return

    async def _collect():
        audio = bytearray()
        comm = Communicate(clean, voice, rate=rate, pitch=pitch)
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                audio.extend(chunk["data"])
        return bytes(audio)

    try:
        audio_bytes = async_to_sync(_collect)()
    except Exception as e:
        self.update_state(state=states.FAILURE, meta={'exc_message': str(e)})
        add_successful_generation("audio", False, f"Ошибка генерации: {e}")
        return

    if not audio_bytes:
        add_successful_generation("audio", False, "Пустой аудиопоток: " + clean)
        self.update_state(state=states.FAILURE, meta={'exc_message': 'Пустой аудиопоток'})
        return

    if len(audio_bytes) > MAX_AUDIO_SIZE:
        add_successful_generation("audio", False, "Аудиофайл слишком большой")
        self.update_state(state=states.FAILURE, meta={'exc_message': 'Аудиофайл слишком большой'})
        return

    add_successful_generation("audio", True, "Successful generation")

    # Можно вернуть аудио в base64, или сохранить в хранилище и вернуть путь
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    return {'audio_base64': audio_b64, 'length_bytes': len(audio_bytes)}

def generate_task_core(user, params):
    """
    Синхронная (обычная) функция, выполняющая ту же логику, что и generate_task_celery,
    но без декоратора Celery. Возвращает dict {'status': 'success', 'data': ...}
    или {'status': 'error', 'message': ...}
    """
    try:
        model_type = 'basic'

        # Обработка изображения (если есть)
        try:
            if 'image_data' in params:
                params['image_data'] = process_image_data(params['image_data'])
                if params['image_data'] is not None:
                    model_type = 'premium'
                else:
                    params['image_data'] = ""
                    model_type = TASK_TYPE_MODEL_PREFERENCE.get(params.get('task_type', ''), 'basic')
            else:
                model_type = TASK_TYPE_MODEL_PREFERENCE.get(params.get('task_type', ''), 'basic')
        except Exception as e:
            print(f"[Warning] Image processing failed in core: {e}")
            model_type = TASK_TYPE_MODEL_PREFERENCE.get(params.get('task_type', ''), 'basic')

        # Получение объекта урока (поднимаем ValueError, если не найден)
        try:
            lesson_obj = get_object_or_404(Lesson, id=params['lesson_id'])
        except Exception as e:
            print(f"[Error] Lesson retrieval failed in core: {e}")
            raise ValueError("Lesson not found")

        # Подготовка запроса
        try:
            if params.get('task_type') == "Audio":
                params['task_type'] = "Transcript"

            base_query, desired_structure = build_base_query(params)
            base_query = enhance_query_with_params(base_query, params)
        except Exception as e:
            print(f"[Warning] Query building failed in core: {e}")
            base_query, desired_structure = "", None

        # Добавление контекста урока
        try:
            auto_context = params.get('auto_context')
            if params.get('context_flag') and not params.get('image_data', False):
                if hasattr(user, 'context_length') and user.context_length:
                    context_length = user.context_length.context_length
                else:
                    context_length = 2000
                context = extract_lesson_context(lesson_obj, auto_context, context_length)
                base_query = context + base_query
            elif auto_context:
                base_query = f"Ты - методист. Мы уже разработали несколько заданий урока: \n{auto_context}\n\n Ты должен разработать задание в дополнение к уроку.\n  {base_query}" if auto_context else base_query
        except Exception as e:
            print(f"[Warning] Context addition failed in core: {e}")

        # Уровень английского
        try:
            english_level = lesson_obj.course.student_level
            base_query = f"Уровень языка: {english_level}. " + base_query
        except Exception as e:
            print(f"[Warning] Adding English level failed in core: {e}")

        # Вызов генератора (AI)
        try:
            print(base_query)
            response = generate_handler(
                user=user,
                query=base_query,
                image_data=params.get('image_data'),
                desired_structure=desired_structure,
                model_type=model_type
            )
        except Exception as e:
            print(f"[Error] Generation handler failed in core: {e}")
            raise

        return {
            'status': 'success',
            'data': response
        }

    except ValueError as e:
        return {'status': 'error', 'message': str(e)}

    except Exception as e:
        print("Error in generate_task_core:", e)
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True)
def generate_task_celery(self, user_id, params):
    """
    Celery-task wrapper: получает пользователя, вызывает generate_task_core и возвращает результат.
    """
    try:
        user = CustomUser.objects.get(id=user_id)
    except Exception as e:
        print(f"[Error] User retrieval failed in celery wrapper: {e}")
        return {'status': 'error', 'message': 'User not found'}

    return generate_task_core(user, params)







import logging
logger = logging.getLogger(__name__)

@shared_task(bind=True)
def generate_lesson_task(self, user_id, lesson_topic, generation_id=None, course_id=None):
    """
    Celery task wrapper.
    Добавлен course_id (опционально) — если передан, генерация привяжется к этому курсу (если он принадлежит user).
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error("User %s does not exist", user_id)
        return {"error": "user_not_found"}

    try:
        from hub.views import generate_lesson
        percent = generate_lesson(user, lesson_topic, generation_id=generation_id, course_id=course_id)
        return {"status": "ok", "percent": percent}
    except Exception as e:
        logger.exception("generate_lesson_task failed: %s", e)
        if generation_id:
            try:
                stat = LessonGenerationStatus.objects.filter(generation_id=generation_id).first()
                if stat:
                    stat.mark_failed()
            except Exception:
                logger.exception("Failed to mark generation status as failed")
        return {"error": str(e)}
