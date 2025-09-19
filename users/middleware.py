from django.utils.deprecation import MiddlewareMixin
from .models import Channel, PromoCode

class ReferralMiddleware(MiddlewareMixin):
    def process_request(self, request):
        ref_code = request.GET.get('ref')
        if ref_code:
            try:
                channel = Channel.objects.get(code=ref_code)
                # Сохраняем в сессию
                request.session['ref_source'] = channel.id
            except Channel.DoesNotExist:
                pass

class PromoMiddleware(MiddlewareMixin):
    def process_request(self, request):
        promo_code = request.GET.get('promo')
        if promo_code:
            request.session['promo_code'] = promo_code
            request.session.modified = True  # обязательно