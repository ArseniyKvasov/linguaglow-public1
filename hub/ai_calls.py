import base64
import random
from urllib.parse import quote_plus
from asgiref.sync import async_to_sync
from django.http import JsonResponse
from django.utils import timezone
from edge_tts import Communicate
from groq import Groq
from google import genai
from google.genai import types
import json, math, re, redis, os, requests
from typing import Any, Optional, Union, Pattern
from django.core.exceptions import PermissionDenied
from .models import SavedUnsplashImage, GenerationStats
from api_endpoints import UNSPLASH_ACCESS_KEY, GROQ_ACCESS_KEY, GOOGLE_API_KEY, PIXABAY_API_KEY



def has_min_tokens(user, min_tokens=5):
    if not user.is_authenticated:
        add_successful_generation("tokens", False, "User not authenticated")
        return False
    try:
        return int(user.token_balance.tokens) >= int(min_tokens)
    except AttributeError:
        add_successful_generation("tokens", False, "Unknown error in has min_tokens")
        return False

def take_tokens(user, cost):
    try:
        balance = user.token_balance
    except AttributeError:
        add_successful_generation("tokens", False, "У пользователя нет баланса токенов" + user.username)
        return False  # У пользователя нет баланса токенов

    # Проверяем, достаточно ли всех токенов
    total_tokens = (balance.tariff_tokens or 0) + (balance.extra_tokens or 0)
    if total_tokens < cost:
        return False  # Недостаточно токенов

    # Списываем сначала с тарифных, потом с дополнительных
    if balance.tariff_tokens >= cost:
        balance.tariff_tokens -= cost
    else:
        remaining = cost - (balance.tariff_tokens or 0)
        balance.tariff_tokens = 0
        balance.extra_tokens = (balance.extra_tokens or 0) - remaining

    balance.save()
    return True




# ИИ

AI_MODELS = [
    {
        "name": "gemma-3-27b-it",
        "day_limit_requests": 14400,
        "is_visual": True,
        "provider": "Google",
        "type": "premium"
    },
    {
        "name": "gemma-3-12b-it",
        "day_limit_requests": 14400,
        "is_visual": False,
        "provider": "Google",
        "type": "basic"
    },
    {
        "name": "gemini-2.0-flash-lite",
        "day_limit_requests": 1500,
        "is_visual": False,
        "provider": "Google",
        "type": "premium"
    },
    {
        "name": "gemini-2.0-flash",
        "day_limit_requests": 1500,
        "is_visual": False,
        "provider": "Google",
        "type": "premium"
    },
    {
        "name": "llama-3.1-8b-instant",
        "day_limit_requests": 14400,
        "is_visual": False,
        "provider": "Groq",
        "type": "basic"
    },
    {
        "name": "llama-3.3-70b-versatile",
        "day_limit_requests": 1000,
        "is_visual": False,
        "provider": "Groq",
        "type": "premium"
    },
    {
        "name": "qwen/qwen3-32b",
        "day_limit_requests": 1000,
        "is_visual": False,
        "provider": "Groq",
        "type": "premium"
    },
    {
        "name": "gemma2-9b-it",
        "day_limit_requests": 14400,
        "is_visual": False,
        "provider": "Groq",
        "type": "basic"
    },
    {
        "name": "meta-llama/llama-4-maverick-17b-128e-instruct",
        "day_limit_requests": 1000,
        "is_visual": True,
        "provider": "Groq",
        "type": "premium"
    }
]

_MULTILINE_STRING_RE: Pattern = re.compile(r'"(?P<key>\w+)":\s*"\s*(?P<value>.*?)\s*"', flags=re.DOTALL)
_BOOL_RE: Pattern = re.compile(r'\b(True|False)\b')

genai_client = genai.Client(api_key=GOOGLE_API_KEY)
client = Groq(api_key=GROQ_ACCESS_KEY)

usage_counters = {m['name']: 0 for m in AI_MODELS}

def generate_handler(user, query: str, desired_structure: str, image_data: Optional[str] = None, model_type: str = "basic") -> str:
    """
    Универсальный хендлер для генерации ответов AI-моделями.
    Принимает дополнительный параметр model_type ("basic" или "premium"),
    по умолчанию — "basic". Сначала пробует модели нужного типа,
    затем — модели другого типа (фоллбэк).
    """
    last_error = None
    tried_models = set()
    max_attempts = 3
    attempts = 0

    if image_data == "":
        image_data = None
    while attempts < max_attempts:
        model = pick_next_model(image_data, model_type, tried_models)
        if not model:
            break
        tried_models.add(model['name'])
        model_name = model['name']
        attempts += 1
        try:
            if model['provider'] == 'Google':
                result = generate_google(
                    user,
                    prompt=query,
                    model=model_name,
                    image_data=image_data,
                    desired_structure=desired_structure
                )
            else:
                result = generate_groq(
                    user,
                    prompt=query,
                    model=model_name,
                    image_data=image_data,
                    desired_structure=desired_structure
                )

            # Проверяем ответ на ошибку API
            if isinstance(result, str):
                last_error = result
                usage_counters[model_name] += 1
                continue

            usage_counters[model_name] += 1
            add_successful_generation("text", True, "Successful generation")
            return result

        except Exception as e:
            last_error = str(e)
            usage_counters[model_name] += 1
            continue

    # Если не найдено подходящих моделей или исчерпаны попытки
    add_successful_generation("text", False, "Unsuccessful generation")
    return (
        "Все модели перегружены. \nОшибка уже передана разработчикам.\n"
        "Воспользуйтесь публичными готовыми уроками - это удобно и быстро\n"
    )

def pick_next_model(image_data: Optional[str], preferred_type: str, tried: set) -> Optional[dict]:
    """
    Выбирает подходящую модель, отдавая приоритет preferred_type ("basic"/"premium").
    С вероятностью 70% выбирает Google-модель, если есть.
    Если модели preferred_type недоступны, ищет среди остальных.
    """
    needs_visual = image_data is not None

    if preferred_type not in ["basic", "premium"]:
        preferred_type = "basic"

    def candidates_for(type_filter):
        cand = []
        for m in AI_MODELS:
            if m['type'] != type_filter:
                continue
            if needs_visual and not m['is_visual']:
                continue
            if m['name'] in tried:
                continue
            used = get_usage(m['name'])
            if used < m['day_limit_requests']:
                remaining = m['day_limit_requests'] - used
                cand.append((m, remaining))
        return cand

    # Сначала пробуем preferred_type
    cand = candidates_for(preferred_type)
    if not cand:
        other_type = "premium" if preferred_type == "basic" else "basic"
        cand = candidates_for(other_type)

    if not cand:
        return None

    # Попробуем с вероятностью 70% выбрать Google
    google_candidates = [m for m, _ in cand if m.get("provider") == "google"]
    if google_candidates and random.random() < 0.7:
        return random.choice(google_candidates)

    # Иначе обычный выбор
    return random.choice(cand)[0]

# helper: получить bytes и mime_type из разных форматов входных данных
def _get_image_bytes_and_mime(src: str):
    """
    src может быть:
        - data URI: data:image/jpeg;base64,/9j/4AAQSk...
        - http/https ссылка
        - чистая base64-строка (jpeg)
    Вернёт (bytes, mime_type) или (None, None) при ошибке.
    """
    try:
        if src.startswith("data:"):
            # формат: data:[<mediatype>][;base64],<data>
            header, b64 = src.split(",", 1)
            mime = header.split(";")[0].split(":", 1)[1] if ";" in header else "image/jpeg"
            img_bytes = base64.b64decode(b64)
            return img_bytes, mime
        elif src.startswith("http://") or src.startswith("https://"):
            resp = requests.get(src, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return resp.content, content_type
        else:
            # предполагаем чистую base64-строку
            try:
                img_bytes = base64.b64decode(src)
                return img_bytes, "image/jpeg"
            except Exception:
                return None, None
    except Exception as e:
        return None, None

def generate_google(user, prompt: str, model: str = "gemma-3-27b-it",
    max_output_tokens: int = 2000, temperature: float = 0.7, top_p: float = 0.8,
    image_data: Optional[str] = None, desired_structure: str = "") -> Union[str, dict, list]:
    if not has_min_tokens(user, min_tokens=-25):
        return "Недостаточно токенов. Пополните баланс."

    # 1) Собираем contents — список элементов, которые передаём в Google GenAI.
    contents = []

    if image_data:
        img_bytes, mime_type = _get_image_bytes_and_mime(image_data)
        if img_bytes:
            try:
                image_part = types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=mime_type
                )
                # как в примерах Google — сначала картинка, потом текст/промпт
                contents.append(image_part)
            except Exception as e:
                print(f"[Warning] Failed to create image Part: {e}")
                # продолжаем без картинки

    # Добавляем текстовую часть (prompt) — можно передать как raw string или Part.from_text
    # В примерах Google допускаются оба варианта; используем Part.from_text для единообразия.
    try:
        text_part = types.Part.from_text(text=prompt)
        contents.append(text_part)
    except Exception:
        # fallback — просто строка
        contents.append(prompt)

    # 2) Делаем запрос
    try:
        gen_config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_output_tokens
        )
        response = genai_client.models.generate_content(
            model=model,
            contents=contents,
            config=gen_config
        )

        incr_usage(model)
        text = response.text

        # 3) Списание токенов
        usage = getattr(response, "usage_metadata", None)
        tokens = getattr(usage, "total_token_count", 0)
        cost = math.ceil(tokens / 100) or 8
        if not take_tokens(user, cost):
            return "Ошибка списания токенов. Проверьте баланс."

        # 4) Парсинг JSON / структуры
        try:
            result = extract_json_or_array_from_text(text, desired_structure)
            if isinstance(result, str) and result.startswith("JSON"):
                # повторный запрос для исправленного JSON
                response2 = genai_client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_text(text=result)],
                    config=gen_config
                )
                result = extract_json_or_array_from_text(response2.text, desired_structure, retry=False)
            return result
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}\nResponse: {text}"

    except Exception as e:
        print(e)
        return f"API Error (Google): {e}"

def generate_groq(user, prompt: str, model: str = "gemma2-9b-it", max_tokens: int = 8191, temperature: float = 0.85, top_p: float = 0.9, stream: bool = False, image_data: Optional[str] = None, desired_structure: str = "") -> Union[str, dict, list]:
    """
    Отправляет запрос в Groq, обрабатывает токены и парсит JSON.

    :return: строка ошибки, dict/list или произвольный ответ
    """
    if not has_min_tokens(user, min_tokens=-25):
        return "Недостаточно токенов. Пополните баланс."

    try:
        client = Groq(api_key=GROQ_ACCESS_KEY)
        msgs = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        if image_data is not None:
            data = image_data.split(',', 1)[1] if image_data.startswith('data:image/') else image_data
            msgs[0]['content'].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{data}"}
            })

        completion = client.chat.completions.create(
            messages=msgs,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        incr_usage(model)
        text = completion.choices[0].message.content

        usage = getattr(completion.usage, 'total_tokens', None)
        cost = math.ceil(usage / 100) if usage else 1
        if not take_tokens(user, cost):
            return "Ошибка списания токенов. Проверьте баланс."

        try:
            result = extract_json_or_array_from_text(text, desired_structure)
            if isinstance(result, str) and result.startswith('JSON'):
                completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": [{"type": "text", "text": result}]}],
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )
                result = extract_json_or_array_from_text(completion.choices[0].message.content, desired_structure, False)
            return result
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}\nResponse: {text}"

    except Exception as e:
        print(e)
        return f"API Error (Groq): {e}"

def clean_multiline_strings(text: str) -> str:
    """
    Удаляет переводы строк внутри значений JSON-строк и сводит их в одну строку.

    :param text: Исходный текст JSON-фрагмента
    :return: Текст с едиными строками значений
    """
    def _replacer(match: re.Match) -> str:
        key = match.group('key')
        raw_value = match.group('value')
        cleaned = ' '.join(line.strip() for line in raw_value.splitlines() if line.strip())
        return f'"{key}": "{cleaned}"'

    return _MULTILINE_STRING_RE.sub(_replacer, text)

def fix_bool_json(text: str) -> str:
    """
    Приводит логические значения Python (True/False) к формату JSON (true/false), избегая изменений внутри строк.

    :param text: Текст с логическими литералами
    :return: Текст с исправленными логическими значениями
    """
    return _BOOL_RE.sub(lambda m: m.group(1).lower(), text)

def extract_first_balanced_json_or_array(text: str) -> Optional[Any]:
    """
    Находит первый сбалансированный JSON-объект или массив в тексте и возвращает его как Python-структуру.

    :param text: Текст, потенциально содержащий JSON-фрагмент
    :return: Распарсенный объект или None
    """
    length = len(text)
    i = 0

    while i < length:
        if text[i] in '{[':
            stack = []
            start = i
            for j in range(i, length):
                char = text[j]
                if char in '{[':
                    stack.append(char)
                elif char in '}]' and stack:
                    opening = stack.pop()
                    if (opening == '{' and char != '}') or (opening == '[' and char != ']'):
                        break
                    if not stack:
                        snippet = text[start:j+1]
                        snippet = clean_multiline_strings(snippet)
                        snippet = fix_bool_json(snippet)
                        try:
                            return json.loads(snippet)
                        except json.JSONDecodeError:
                            break
            i = j + 1
        else:
            i += 1
    return None

def extract_json_or_array_from_text(text: str, desired_structure: str, retry: bool = True) -> Union[str, dict, list]:
    """
    Извлекает JSON-объект или массив из текста.

    1) Поиск в markdown-код-блоках ```json``` и ```...```.
    2) Парсинг сбалансированных фрагментов.
    3) Прямой срез от первой '{' до последней '}'.
    4) При неудаче возвращает подсказку для повторного запроса или исходный текст.

    :param text: Входной текст с возможным JSON
    :param desired_structure: Ожидаемый шаблон структуры для подсказки
    :param retry: Разрешить возвращать подсказку для повторного запроса
    :return: Распарсенный JSON или строка/исходный текст
    """
    # 1) Извлечение код-блоков
    code_blocks = re.findall(r'```json(.*?)```', text, flags=re.DOTALL | re.IGNORECASE)
    code_blocks += re.findall(r'```(.*?)```', text, flags=re.DOTALL)

    # 2) Парсим каждый блок
    for block in code_blocks:
        parsed = extract_first_balanced_json_or_array(block)
        if parsed is not None:
            return parsed

    # 3) Попытка прямого среза
    try:
        start = text.index('{')
        end = text.rindex('}') + 1
        snippet = text[start:end]
        snippet = clean_multiline_strings(snippet)
        snippet = fix_bool_json(snippet)
        return json.loads(snippet)
    except (ValueError, json.JSONDecodeError):
        pass

    # 4) Подсказка для повторного запроса
    if retry:
        return f"{desired_structure} Incorrect the following and write only json: {text}"

    # 5) Если всё не удалось — возвращаем исходный текст
    return text

# Подсчет лимитов

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.Redis.from_url(REDIS_URL)

def _get_today_key(model_name: str) -> str:
    from datetime import date
    return f"usage:{model_name}:{date.today().isoformat()}"

def get_usage(model_name: str) -> int:
    """Возвращает количество использованных запросов сегодня из Redis"""
    key = _get_today_key(model_name)
    val = redis_client.get(key)
    return int(val) if val is not None else 0

def incr_usage(model_name: str) -> None:
    """Увеличивает счётчик запросов для модели и устанавливает TTL на конец дня"""
    key = _get_today_key(model_name)
    # Начинать счетчик с 0, затем INCR
    new_val = redis_client.incr(key)
    # Установить истечение в полночь, если впервые
    if new_val == 1:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        # время до следующего дня
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds = int((tomorrow - now).total_seconds())
        redis_client.expire(key, seconds)




# Изображения
def search_images_api(query: str, page: int = 1, user=None):
    if user is None or not getattr(user, 'is_authenticated', False):
        raise PermissionDenied("User must be authenticated for token deduction")

    # Проверяем токены и списываем
    if not has_min_tokens(user, min_tokens=1) or not take_tokens(user, cost=1):
        raise PermissionDenied("Недостаточно токенов для выполнения поиска")

    # Очищаем запрос
    query_clean = re.sub(r"\s+", ' ', query.strip())

    # 1) Сначала проверяем в БД сохранённые картинки по запросу
    saved_images = SavedUnsplashImage.objects.filter(query__iexact=query_clean)
    if saved_images.exists():
        # Возвращаем до 20 последних записей
        results = saved_images.order_by('-created_at')[:20]
        return {'images': [{'url': img.url, 'title': img.title} for img in results]}

    # 2) Если в БД нет, делаем запрос к Unsplash
    encoded = quote_plus(query_clean)
    url = "https://api.unsplash.com/search/photos"
    params = {
        'query': encoded,
        'page': page,
        'per_page': 15,
        'client_id': UNSPLASH_ACCESS_KEY,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if 'results' not in data:
        add_successful_generation("images", False, "Invalid response from Unsplash API")
        raise ValueError("Invalid response from Unsplash API")

    images = []
    count = 0
    # 3) Сохраняем до 20 с title длиной <=10
    for item in data['results']:
        if count >= 20:
            break
        title = item.get('alt_description') or ''
        title = title.strip()
        if len(query_clean) <= 10:
            url_img = item['urls'].get('regular')
            if url_img:
                # Сохраняем в БД
                try:
                    SavedUnsplashImage.objects.create(
                        query=query_clean,
                        url=url_img,
                        title=title
                    )
                except Exception:
                    # возможен IntegrityError при дубле, пропускаем
                    pass
                images.append({'url': url_img, 'title': title})
                count += 1

    return {'images': images}

"""
def search_images_api(query: str, page: int = 1, user=None):
    if user is None or not getattr(user, 'is_authenticated', False):
        raise PermissionDenied("User must be authenticated for token deduction")

    # Проверяем токены и списываем
    if not has_min_tokens(user, min_tokens=1) or not take_tokens(user, cost=1):
        raise PermissionDenied("Недостаточно токенов для выполнения поиска")

    # Очищаем запрос
    query_clean = re.sub(r"\s+", ' ', query.strip())

    # 1) Сначала проверяем в БД сохранённые картинки по запросу
    saved_images = SavedUnsplashImage.objects.filter(query__iexact=query_clean)
    if saved_images.exists():
        results = saved_images.order_by('-created_at')[:20]
        return {'images': [{'url': img.url, 'title': img.title} for img in results]}

    # 2) Если в БД нет, делаем запрос к Pixabay
    encoded = quote_plus(query_clean)
    url = "https://pixabay.com/api/"
    params = {
        'key': PIXABAY_API_KEY,
        'q': encoded,
        'page': page,
        'per_page': 15,
        'image_type': 'photo',
        'safesearch': 'true',
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    if 'hits' not in data:
        add_successful_generation("images", False, "Invalid response from Pixabay API")
        raise ValueError("Invalid response from Pixabay API")

    images = []
    count = 0

    # 3) Сохраняем до 20 с title длиной <=10
    for item in data['hits']:
        if count >= 20:
            break
        title = item.get('tags') or ''
        title = title.strip()
        if len(query_clean) <= 10:
            url_img = item.get('webformatURL')
            if url_img:
                try:
                    SavedUnsplashImage.objects.create(
                        query=query_clean,
                        url=url_img,
                        title=title
                    )
                except Exception:
                    pass
                images.append({'url': url_img, 'title': title})
                count += 1

    return {'images': images}
"""

def search_images(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
        query = data.get('query', '')
        page = int(data.get('page', 1))

        if not query.strip():
            return JsonResponse({'error': 'Query is required'}, status=400)

        # Передаем user внутрь search_images_api
        result = search_images_api(query, page, user=request.user)
        return JsonResponse(result)

    except PermissionError as e:
        return JsonResponse({'error': str(e)}, status=403)
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'error': str(e)}, status=400)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Request error: {str(e)}'}, status=500)
    except Exception as e:
        print(e)
        return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)








def add_successful_generation(type: str, is_successful: bool, error_text: str):
    # Валидируем type
    valid_types = {'images', 'audio', 'text', 'tokens', 'functions'}
    if type not in valid_types:
        raise ValueError(f"Invalid type '{type}'. Must be one of {valid_types}")

    # Берём сегодняшнюю дату (без времени)
    today = timezone.now().date()

    # Пытаемся получить запись для данного типа и сегодняшнего дня
    obj, created = GenerationStats.objects.get_or_create(
        type=type,
        created_at__date=today,
        error_text=error_text,
        defaults={'successful_generations': 0, 'unsuccessful_generations': 0}
    )

    # Обновляем счётчики
    if is_successful:
        obj.successful_generations += 1
    else:
        obj.unsuccessful_generations += 1

    obj.save()