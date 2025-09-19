# Запрос к ИИ
import json
import random
import re
from bs4 import BeautifulSoup
from django.http import JsonResponse



def extract_base64_image(image_data):
    """Извлекает base64-строку из data URL"""
    if isinstance(image_data, str) and image_data.startswith('data:image/'):
        try:
            return image_data.split(',')[1]
        except IndexError:
            raise ValueError("Invalid image format")
    elif image_data:
        raise ValueError("Expected base64-encoded image in data URL format")
    return None

def process_image_data(image_data):
    """Process and validate image data if present"""
    if not image_data:
        return None

    if isinstance(image_data, str) and image_data.startswith('data:image/'):
        return image_data.split(',')[1]

    raise ValueError('Invalid image format. Expected base64 data URL.')

def extract_lesson_context(lesson_obj, auto_context, max_chars):
    """Извлекает контекст из урока и auto_context, возвращает строку с приоритетом конца, с префиксом SYSTEM CONTEXT."""
    from hub.views import normalize

    lesson_context = lesson_obj.context
    full_text = ""

    # Собираем весь контекст из lesson_context в одну строку
    for key, value in lesson_context.items():
        if key == "base":
            continue

        header_raw = value.get("header", "")
        header = normalize(header_raw.strip() if header_raw else "")

        content = value.get("content", "")

        if header == "список слов":
            bold_words = re.findall(r"<b>(.*?)</b>", content)
            clean = [normalize(w).strip() for w in bold_words if normalize(w).strip()]
            if clean:
                full_text += f"{header}: {', '.join(clean)}. "
        else:
            text = BeautifulSoup(content, "html.parser").get_text()
            text = normalize(text)
            text = re.sub(r'[^\w\s,.\-!?]', '', text).strip()
            if text:
                full_text += f"{header}: {text}. "

    # Добавляем auto_context, если есть
    if auto_context:
        auto_context_text = " ".join(normalize(line) for line in auto_context)
        if auto_context_text:
            full_text += auto_context_text

    full_text = full_text.strip()

    # Обрезаем строку с приоритетом конца (срезаем спереди, чтобы сохранить конец)
    if len(full_text) > max_chars:
        full_text = full_text[-max_chars:].lstrip()

    return f"Ты - методист. Мы уже разработали несколько заданий урока: \n{full_text}\n\n Ты должен разработать задание в дополнение к уроку.\n" if full_text else ""

def update_auto_context(auto_context, task_type, result):
    """
    Добавляет строку в auto_context на основе task_type и result.
    Гарантирует, что:
    - первый элемент в auto_context сохраняется;
    - длина итоговой строки auto_context не превышает 3000 символов.
    """
    if not isinstance(auto_context, list):
        auto_context = []

    new_line = ""

    if task_type == "WordList":
        words = result.get("words", [])
        if isinstance(words, list):
            pairs = ", ".join(
                f"{item['word']} - {item['translation']}"
                for item in words
                if isinstance(item, dict)
                and isinstance(item.get("word"), str)
                and isinstance(item.get("translation"), str)
            )
            new_line = "Word list: " + pairs + "; "

    elif task_type == "Note":
        content = result.get("content", "")
        if isinstance(content, str):
            new_line = "Note: " + content + "; "

    elif task_type == "Article":
        content = result.get("content", "")
        if isinstance(content, str):
            new_line = "Article: " + content + "; "

    elif task_type == "Audio":
        content = result.get("transcript", "")
        if isinstance(content, str):
            new_line = "Audio: " + content + "; "

    if not new_line:
        return auto_context  # ничего не добавлять

    # Обновляем список
    fixed_first = auto_context[0] if auto_context else ""
    rest = auto_context[1:] if len(auto_context) > 1 else []

    rest.append(new_line)

    # Ограничиваем по длине
    while len('\n'.join([fixed_first] + rest)) > 3000 and rest:
        rest.pop(0)

    return [fixed_first] + rest if fixed_first else rest

def build_base_query(params):
    """Construct the base query based on task type and parameters"""
    task_type = params.get('task_type')
    user_query = params.get('user_query')
    language = params.get('language', 'en')  # Например, по умолчанию английский
    fill_type = params.get('fill_type')  # Можно оставить None
    match_type = params.get('match_type')
    is_copy = params.get('is_copy', False)  # Нововведенный параметр

    # Ограничение длины user_query
    if is_copy:
        user_query = user_query[:2000]  # Ограничение до 2000 символов для копирования
    else:
        user_query = user_query[:255]  # Ограничение до 255 символов для не копирования

    queries = {
        "WordList": {
            "base": "Составь список слов на английском",
            "copy_base": "Отформатируй список слов в JSON",
            "user_query": f"{user_query}.",
            "suffix": "",
            "structure": "JSON {'title': str, 'words': [{'word': str, 'translation': str}]}"
        },
        "Note": {
            "base": "Напиши заметку",
            "copy_base": "Отформатируй в JSON.",
            "user_query": f"{user_query}" if user_query else " в продолжение урока",
            "suffix": ". Используй форматирование.",
            "structure": "JSON {'title': str, 'content': str}"
        },
        "FillInTheBlanks": {
            "base": f"Составить  {get_fill_type_description(fill_type)} задание заполнить пропуски.",
            "copy_base": f"Отформатируй задание заполнить пропуски в JSON. В каждом предложении только один пропкуск (отметь как _).",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": " В каждом предложении только один пропкуск (отметь как _). Не стоит брать предложения 1 в 1 из контекста.",
            "structure": "JSON {'title': str, 'sentences': [{'text': str, 'answer': str}]}"
        },
        "MatchUpTheWords": {
            "base": f"Составь задание на соотношение пар {get_match_type_description(match_type)}.",
            "copy_base": f"Отформатируй задание на соотношение пар в JSON. Нужно записать пары корректно и без нумерации/маркеров.",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'pairs': [{'card1': str, 'card2': str}]}"
        },
        "Article": {
            "base": f"Составь раздел чтения на {'английском' if language == 'en' else 'русском'}. Используй форматирование.",
            "copy_base": f"Отформатируй блок чтения в JSON. Используй форматирование.",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'content': str}"
        },
        "Test": {
            "base": f"Составь тест на {'английском' if language == 'en' else 'русском'}.",
            "copy_base": f"Отформатируй тест в JSON",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'questions': [{'text': str, 'answers': [{'text': str, 'is_correct': bool}]}]}"
        },
        "TrueOrFalse": {
            "base": f"Составь утверждения правда/ложь на {'английском' if language == 'en' else 'русском'}",
            "copy_base": f"Format True/False questions into JSON",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": ". Questions should be clear.",
            "structure": "JSON {'title': str, 'statements': [{'text': str, 'is_true': bool}]}"
        },
        "MakeASentence": {
            "base": f"Составь короткие предложения на английском языке. ",
            "copy_base": f"Запиши предложение корректно, потом отформатируй в JSON.",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "Не стоит использовать предложения 1-в-1 как в контексте.",
            "structure": "JSON {'title': str, 'sentences': [{'sentence': str}]}"
        },
        "SortIntoColumns": {
            "base": "Составь задание на сортировку на английском.",
            "copy_base": "Отформатируй задание на сортировку в JSON",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'columns': [{'name': str, 'words': [str]}]}"
        },
        "Essay": {
            "base": "Придумай интересную тему для письма на английском.",
            "copy_base": "Отформатируй тему эссе JSON.",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str}"
        },
        "Transcript": {
            "base": "Составь транскрипт монолога на английском.",
            "copy_base": "Отформатируй текст в транскрипт монолога на английском JSON",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'transcript': str}"
        },
        "LabelImages": {
            "base": "Придумай названия для картинок, которые я найду для урока.",
            "copy_base": "Отформатируй подписи картинок в JSON",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'labels': [str]}"
        },
        "Unscramble": {
            "base": "Выбери слова на английском и добавь к ним подсказки.",
            "copy_base": "Отформатируй список слов в JSON и добавь подсказки.",
            "user_query": f"{user_query}" if user_query else "",
            "suffix": "",
            "structure": "JSON {'title': str, 'words': [{'word': str, 'hint': str}]}"
        }
    }

    if task_type not in queries:
        raise ValueError('Invalid task type')

    query_info = queries[task_type]

    if is_copy:
        base_query = f" {query_info['structure']}." + query_info.get('copy_base', '') + query_info.get('user_query', '')
    else:
        base_query = query_info['base'] + query_info.get('user_query', '') + query_info['suffix'] + f" {query_info['structure']}."

    return base_query, query_info['structure']

def get_fill_type_description(fill_type):
    """Get description for fill type"""
    return {
        'lexical': "лексическое",
        'grammar': "грамматическое (с указаниями в круглых скобках)",
        None: ""
    }.get(fill_type, "")

def get_match_type_description(match_type):
    """Get description for match type"""
    return {
        'word-translate': "слово - перевод",
        'question-answer': "вопрос - ответ",
        'beginning-continuation': "начало диалога - ответ",
        'card1-card2': "",
        None: ""
    }.get(match_type, "")

def enhance_query_with_params(base_query, params):
    """Enhance the base query with additional parameters"""
    emoji = params.get('emoji', False)

    if emoji:
        base_query += " Добавь эмодзи."

    return base_query

def markdown_to_html(text: str) -> str:
    """
    Преобразует базовый Markdown-текст в HTML без сторонних библиотек.
    Поддержка: жирный, курсив, списки, ссылки.
    """
    # Экранируем HTML специальные символы
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Жирный **текст**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Курсив *текст*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Ссылки [текст](url)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)

    # Списки - элемент
    def replace_list(match):
        items = match.group(0).strip().split('\n')
        items = [f'<li>{item[2:]}</li>' for item in items]
        return '<ul>\n' + '\n'.join(items) + '\n</ul>'

    text = re.sub(r'((?:^- .+\n?)+)', replace_list, text, flags=re.MULTILINE)

    # Абзацы
    lines = text.split('\n')
    html_lines = []
    for line in lines:
        if line.strip() and not re.match(r'^<.*?>.*</.*?>$', line.strip()):
            html_lines.append(f'<p>{line.strip()}</p>')
        else:
            html_lines.append(line)

    return '\n'.join(html_lines)

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

def shuffle_sentence(sentence: str) -> str:
    words = sentence.strip().split()
    random.shuffle(words)
    shuffled = " ".join(words)
    return shuffled