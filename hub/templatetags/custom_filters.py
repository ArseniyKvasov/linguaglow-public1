import json
import base64
import re
import random

from django import template

register = template.Library()

@register.filter
def format_tokens(value):
    """
    Заменяет последние '000' на '.000'.
    1000 -> 1.000
    2000 -> 2.000
    25000 -> 25.000
    250 -> 250 (без изменений)
    """
    try:
        value = str(int(value))
    except (ValueError, TypeError):
        return value

    if value.endswith("000"):
        return value[:-3] + " 000"
    return value

@register.filter
def get_current_user(request):
    """Возвращает текущего пользователя (учителя) из запроса."""
    return request.user

@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return ''

@register.filter
def div(value, arg):
    try:
        return float(value) / float(arg)
    except:
        return ''

@register.filter
def to_int(value):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)