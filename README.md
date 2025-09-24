# 🌐 LinguaGlow

**LinguaGlow** — это платформа для преподавания иностранных языков с генерацией заданий с помощью ИИ и виртуальным классом в реальном времени.

---

## 🚀 Возможности

* 📚 15 шаблонов заданий с AI-генерацией: заполнить пропуски, сопоставление, варианты ответа, диалоги и др.
* 🎯 Контекстная генерация: задания подстраиваются под тему урока и уровень студентов.
* ⚡ Быстрая сборка урока: создать готовый план занятия в два клика.
* 📝 Экспорт урока в PDF: красиво оформленный файл доступен для скачивания.
* 🎥 Встроенные видеозвонки: Jitsi прямо в кабинете.
* 💳 Приём платежей через YooKassa.
* 🔄 Асинхронная обработка: Celery + Redis для тяжёлых задач (генерация, PDF).
* ✉️ Email-рассылки: уведомления, напоминания и промо.
* 🔗 Интеграции: WordWall, Quizlet, YouTube.
* 🔊 Генерация аудио через edge-tts.
* 🖥 Виртуальный класс: realtime-сессии на WebSocket + Redis.

---

## 🧠 Технологии

* ⚙️ **Backend:** Django + Django Channels (ASGI)
* ⏱ **Асинхронность:** Celery + Redis
* 🗄 **Хранение:** PostgreSQL
* 🌐 **Realtime:** WebSocket (Channels) + Uvicorn/Nginx
* 💻 **Frontend:** JavaScript, Bootstrap, адаптивный UI (teacher / student / admin)
* 🤖 **AI:** GenAI / Groq (генерация контента)
* 🔊 **Audio:** edge-tts
* 🎥 **Видео:** Jitsi
* 💳 **Платежи:** YooKassa
* ✉️ **Email:** API SMTP-сервиса

---

## 💡 Сильные стороны

* 🚀 Экономия времени преподавателя: готовый урок за минуты.
* 🧩 Модульная архитектура: легко расширять новыми шаблонами.
* ⚡ Масштабируемость: асинхронность и хранение файлов в облаке.
* 🔗 Интеграции: WordWall, Quizlet, YouTube.


---

## 🔧 Запуск проекта

Чтобы запустить проект локально или на сервере, необходимо:

1. Ввести свои ключи в файлы:
   * linguaglow/settings.py
   * .env
   ```ini
   # API Keys
   UNSPLASH_ACCESS_KEY=your_unsplash_key
   PIXABAY_API_KEY=your_pixabay_key
   GROQ_ACCESS_KEY=your_groq_key
   GOOGLE_API_KEY=your_google_key

   YANDEX_CLIENT_ID=your_yandex_client_id
   YANDEX_CLIENT_SECRET=your_yandex_client_secret

   SMTPBZ_API_KEY=your_smtpbz_key

2. Настроить сервисы:
   * **Celery** — для асинхронных задач (генерация, PDF).
   * **Uvicorn / Gunicorn** — для запуска Django (ASGI).
   * (опционально) **Nginx** — для проксирования и статики.

После этого проект будет готов к работе 🚀
