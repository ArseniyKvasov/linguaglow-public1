from django.contrib import admin
from .models import CustomUser, Notification

# Register your models here.
admin.site.register(CustomUser)
admin.site.register(Notification)