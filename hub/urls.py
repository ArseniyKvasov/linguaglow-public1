from django.urls import path

from . import views, ai_calls

urlpatterns = [
    path("robots.txt", views.robots_txt),
    path('sitemap.xml', views.sitemap_view, name='sitemap'),
    path('', views.landing, name='landing'),
    path('home/', views.home_view, name='home'),
    path('user/context-length/save/', views.save_context_length, name='save_context_length'),
    path('api/update-subscription/', views.update_subscription, name='update_subscription'),
    path('shop/', views.shop_view, name='shop'),
    path('create-course/', views.create_course, name='create_course'),
    path('course/<uuid:course_id>/delete/', views.delete_course, name='delete_course'),
    path('course/<uuid:course_id>/lessons/', views.lesson_list_view, name='lesson_list'),
    path('course/<uuid:course_id>/lessons/add/', views.add_lesson, name='add_lesson'),
    path("lessons/<uuid:lesson_id>/update_name/", views.update_lesson_name, name="update_lesson_name"),
    path('lessons/<int:lesson_id>/update/', views.update_lesson, name='update_lesson'),
    path('lesson/<uuid:lesson_id>/', views.lesson_page_view, name='lesson_page'),
    path('lesson/<uuid:lesson_id>/delete/', views.delete_lesson, name='delete_lesson'),
    path('lesson/<uuid:lesson_id>/add_section/', views.add_section, name='add_section'),
    path('lessons/<uuid:lesson_id>/update/', views.update_lesson, name='update_lesson'),
    path("lessons/<uuid:lesson_id>/reorder_sections/", views.reorder_sections, name="reorder_sections"),
    path('section/<uuid:section_id>/update', views.update_section, name='update_section'),
    path('section/<uuid:section_id>/delete/', views.delete_section_view, name='delete_section'),
    path('section/<uuid:section_id>/task/save', views.taskSave, name='save_task'),
    path('api/tasks/<uuid:task_id>/', views.get_task_data, name='get_task_data'),
    path('api/section/<uuid:section_id>', views.get_section_tasks, name='get_section_tasks'),
    path('tasks/<uuid:task_id>/delete/', views.delete_task, name='delete_task'),
    path('api/get-course-pdfs/', views.get_course_pdfs, name='get_pdfs'),

    path('lesson/<uuid:lesson_id>/download-pdf/', views.download_pdf_page_view, name='download_pdf'),
    path('qr/audio/<path:audio_url>/', views.audio_qr_page, name='audio_qr_page'),
    path('qr/iframe/lz/<str:compressed_code>/', views.iframe_qr_page, name='iframe_qr_page'),

    path('classroom/<uuid:classroom_id>/', views.classroom_view, name='classroom_view'),
    path('courses/<uuid:course_id>/select-lesson/', views.select_lesson_for_course, name='course_select_lesson'),
    path("choose-classroom/<uuid:lesson_id>/", views.choose_classroom, name="choose_classroom"),
    path('create-classroom/', views.create_classroom_without_lesson, name='create_classroom'),
    path('create-classroom/<uuid:lesson_id>/', views.create_classroom_with_lesson, name='create_classroom_with_lesson'),
    path('classrooms/<uuid:classroom_id>/delete/', views.delete_classroom, name='delete_classroom'),
    path('classroom/<uuid:classroom_id>/toggle-copying/', views.toggle_copying, name='toggle_copying'),
    path('classroom/<uuid:classroom_id>/send-homework-page/', views.send_homework_page_view, name='send_homework_page'),
    path('send-homework/', views.send_homework, name='send_homework'),
    path('classroom/<uuid:classroom_id>/homework/<uuid:lesson_id>/', views.homework_view, name='classroom_homework_view'),
    path('api/jitsi/token/', views.get_jitsi_token, name='get_jitsi_token'),
    path('submit-homework/', views.submit_homework, name='submit_homework'),

    path('invitation/<str:code>/', views.accept_invitation, name='accept_invitation'),
    path('invitation/expired/', views.invitation_expired, name='invitation_expired'),
    path('invitation/not-found/', views.invitation_not_found, name='invitation_not_found'),

    path('search-images/', ai_calls.search_images, name='search_images'),

    path('api/receive-answer/', views.receiveAnswer, name='receive_answer'),

    path('add-context-element/<uuid:lesson_id>/', views.addContextElement, name='add_context_element'),
    path('remove-context-element/<uuid:lesson_id>/<str:task_id>/', views.removeTaskFromContext, name='remove_task_from_context'),
    path('context/<uuid:lesson_id>/get/', views.getContext, name='get_context'),

    path('generate-request/', views.generate_request, name='generate_request'),
    path('get-task-status/<str:task_id>/', views.get_task_status, name='get_task_status'),

    path('separate-blocks/', views.separate_into_blocks, name='separate_into_blocks'),
    path("start-block-generation/", views.start_block_generation, name="start_block_generation"),
    path("block-generation-status/<uuid:generation_id>/", views.block_generation_status, name="block_generation_status"),
    path("api/create-section/", views.create_section, name="create_section"),
    path('form-block/', views.form_block, name='form_block'),

    path("api/standart-pattern/<uuid:course_id>", views.standart_pattern, name="standart_pattern"),

    path("generate-pdf/", views.handle_pdf_upload, name="generate_pdf"),
    path("pdf-status/<uuid:task_id>/", views.get_pdf_status_view, name="pdf_status"),
    path('save-autogen-preferences/<uuid:course_id>/', views.save_autogen_preferences, name='save_autogen_preferences'),
    path('get-autogen-preferences/<uuid:course_id>/', views.get_autogen_preferences, name='get_autogen_preferences'),

    path("api/reorder-tasks/", views.reorder_tasks, name="reorder_tasks"),
    path('api/get_answers/', views.getAnswers, name='get_answers'),
    path("api/delete_answers/", views.delete_answers, name="delete_answers"),
    path('api/edge-tts/', views.edge_tts_view, name='edge_tts'),
    path('api/edge-tts/status/<uuid:task_id>/', views.edge_tts_status_view, name='edge_tts_status'),

    # Публичные уроки
    path('public/<slug:link_name>/', views.public_lesson_view, name='public_lesson'),
    path('api/get-complex-answers/', views.get_complex_tasks_answers, name='complex_answers'),

    path('connect-tariff/', views.connect_tariff, name='connect_tariff'),
    path('connect-tokens/', views.connect_tokens, name='connect_tokens'),
    path('api/report-error/', views.report_site_error, name='report_error'),

    path('payments/connect-tokens/', views.connect_tokens, name='connect_tokens'),
    path('payments/return/', views.tokens_return, name='return'),

    path('api/subscribe/', views.subscribe_emails, name='subscribe'),
    path('api/switch-role/', views.switch_role, name='switch_role'),

    path('lesson/select/', views.select_lesson, name='select_lesson'),
    path("api/lessons/generate", views.start_generate_lesson, name="generate_lesson"),
    path("api/lessons/generation-status/<uuid:generation_id>/", views.get_generation_status, name="generate_lesson_status"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/update/", views.onboarding_update, name="onboarding_update"),

    path('public-lessons/', views.public_lessons, name='public_lessons'),
    path('public-lesson/<uuid:lesson_id>/', views.public_lesson_preview, name='public_lesson_preview'),
    path("download/pdf/<uuid:lesson_id>/", views.download_public_pdf, name="download_public_pdf"),
    path("api/pdf/downloaded/", views.pdf_downloaded, name="pdf_downloaded"),
    path('subscribe/', views.subscribe_email, name='subscribe_email'),
    path("link-telegram/", views.link_telegram, name="link_telegram"),

    path('articles/invitation-guide/', views.invitation_guide, name='invitation_guide'),
    path('articles/course-guide/', views.course_guide, name='course_guide'),
]

