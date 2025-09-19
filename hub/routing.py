from django.urls import path
from .consumers import ClassConsumer

websocket_urlpatterns = [
    path("ws/classroom/<uuid:classroom_id>/", ClassConsumer.as_asgi()),
]
