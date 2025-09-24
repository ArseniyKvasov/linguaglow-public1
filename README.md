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

1. Создать файл `.env` в корне проекта и добавить туда ключи:

   # API Keys
   UNSPLASH_ACCESS_KEY=your_unsplash_key
   PIXABAY_API_KEY=your_pixabay_key
   GROQ_ACCESS_KEY=your_groq_key
   GOOGLE_API_KEY=your_google_key
   SMTPBZ_API_KEY=your_smtpbz_key

2. Установить зависимости:

   ```bash
   pip install -r requirements.txt
   ```

3. Выполнить миграции и собрать статику:

   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```

4. Запустить сервер:

   * Локально (**Uvicorn**):

     ```bash
     uvicorn linguaglow.asgi:application --reload
     ```
   * В продакшене (**Gunicorn + UvicornWorker**):

     ```bash
     gunicorn linguaglow.asgi:application -k uvicorn.workers.UvicornWorker
     ```

5. Запустить **Celery** для асинхронных задач:

   ```bash
   celery -A linguaglow worker -l info
   celery -A linguaglow beat -l info
   ```

6. (опционально) Настроить **Nginx** для проксирования и отдачи статики.

После этих шагов проект будет готов к работе 🚀
