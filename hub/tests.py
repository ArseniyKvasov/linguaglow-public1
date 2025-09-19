from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
import uuid
from django.contrib.contenttypes.models import ContentType
from hub.models import Course, Lesson, Section, BaseTask, WordList, Classroom
from django.test import TransactionTestCase
from channels.testing import WebsocketCommunicator
from linguaglow.asgi import application

User = get_user_model()

class AuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.username = "testuser"
        self.password = "7876uiuy"
        self.user = User.objects.create_user(username=self.username, password=self.password, role="teacher")

    def test_login(self):
        response = self.client.post(reverse("login"), {"username": self.username, "password": self.password})
        self.assertEqual(response.status_code, 302)  # редирект после логина

    def test_logout(self):
        self.client.login(username=self.username, password=self.password)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)  # редирект после логаута

class CourseCreationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="teacher", password="12345", role="teacher")
        self.client.login(username="teacher", password="12345")

    def test_create_course(self):
        c = Course.objects.create(name="English A1", user=self.user)
        self.assertEqual(c.name, "English A1")
        self.assertEqual(str(c), "English A1")

class LessonStructureTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teach", password="123", role="teacher")
        self.course = Course.objects.create(name="Test course", user=self.teacher)
        self.lesson = Lesson.objects.create(name="Lesson 1", course=self.course)
        self.section = Section.objects.create(name="Section A", lesson=self.lesson, order=1)
        self.wordlist = WordList.objects.create(title="Animals", words=["cat", "dog"])
        self.task = BaseTask.objects.create(
            section=self.section,
            order=1,
            content_type = ContentType.objects.get_for_model(self.wordlist),
            object_id=self.wordlist.id,
            size=1
        )

    def test_lesson_hierarchy(self):
        self.assertEqual(self.lesson.course, self.course)
        self.assertEqual(self.section.lesson, self.lesson)
        self.assertEqual(self.task.section, self.section)


class WebSocketTest(TransactionTestCase):

    async def test_websocket_connection(self):
        # Создаем пользователя-учителя
        user = User.objects.create_user(username='teacher1', password='pass', role='teacher')

        # Генерируем UUID для classroom (должен совпадать с URL)
        classroom_id = uuid.UUID("d36f9a15-2fe9-4154-9a32-7d770299f3c1")

        # Создаем класс и назначаем учителя
        classroom = Classroom.objects.create(id=classroom_id, name="Test Classroom")
        classroom.teachers.add(user)
        classroom.save()

        communicator = WebsocketCommunicator(application, f"/ws/classroom/{classroom_id}/")
        communicator.scope['user'] = user  # подменяем аутентифицированного пользователя

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    def test_run_ws_test(self):
        import asyncio
        asyncio.run(self.test_websocket_connection())