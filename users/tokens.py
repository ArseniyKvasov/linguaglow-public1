import hashlib

from django.conf import settings


def generate_unsubscribe_token(user):
    salt = settings.SECRET_KEY[:10]
    raw = f"{user.id}{user.email}{salt}"
    return hashlib.sha256(raw.encode()).hexdigest()