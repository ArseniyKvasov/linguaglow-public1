from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('verify-email/', views.verify_email_view, name='verify_email'),
    path('send-verification-code/', views.send_verification_code, name='send_verification_code'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-code/', views.verify_code, name='verify_code'),

    path('documents/', views.documents, name='documents'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('notifications/hide/<int:notification_id>/', views.hide_notification, name='hide_notification'),

    path('stats/', views.website_stats, name='website_stats'),
    path('admin/delete-error/<int:pk>/', views.delete_site_error, name='delete_site_error'),
    path('admin/notifications/delete/<int:pk>/', views.delete_notification, name='delete_notification'),
    path('admin/email-template/save/', views.create_or_update_email_template, name='save_email_template'),
    path('admin/email-template/delete/', views.delete_email_template, name='delete_email_template'),
    path('api/send-email-template/', views.send_email_template, name='send_email_template'),
    path('api/email-task-status/<str:task_id>/', views.check_email_task_status, name='check_email_task_status'),
    path('channels/create/', views.create_channel, name='create_channel'),
    path('channels/delete/<int:pk>/', views.delete_channel, name='delete_channel'),
    path('create-promo/', views.create_promo, name='create_promo'),
    path('delete-promo/<int:promo_id>/', views.delete_promo, name='delete_promo'),

    path("unsubscribe/", views.unsubscribe_page, name="unsubscribe_page"),
    path("unsubscribe/confirm/", views.unsubscribe_confirm, name="unsubscribe_confirm"),

    path("fastlesson/", views.fastlesson, name="fastlesson"),

    path('studynote/', views.studynote, name='studynote'),
    path("studynote/thanks/", TemplateView.as_view(template_name="home/thanks.html"), name="thanks"),
    path("applications/<int:pk>/delete/", views.delete_application, name="delete_application"),

    path("arseniy/", views.tutor_profile, name="tutor_profile"),
    path("arseniy/query/", views.handle_application, name="handle_application"),
    path("arseniy/delete/<int:pk>/", views.delete_application, name="delete_application"),
]