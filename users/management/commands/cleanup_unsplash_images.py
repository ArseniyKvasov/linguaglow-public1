from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from ...models import SavedUnsplashImage

class Command(BaseCommand):
    help = 'Удаляет записи SavedUnsplashImage старше одного года'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=365)
        deleted, _ = SavedUnsplashImage.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Удалено {deleted} старых записей изображений.")
