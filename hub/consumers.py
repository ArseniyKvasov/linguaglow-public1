import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class ClassConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.classroom_id = self.scope['url_route']['kwargs']['classroom_id']
        self.class_group = f'class_{self.classroom_id}'
        self.user_group = f'user_{self.user.id}'

        self.is_teacher = await self._is_teacher()

        await self.accept()
        await self.channel_layer.group_add(self.class_group, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        role = "Teacher" if self.is_teacher else "Student"
        print(f"{role} connected: user_id={self.user.id}, channel={self.channel_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.class_group, self.channel_name)
        await self.channel_layer.group_discard(self.user_group, self.channel_name)

        role = "Teacher" if self.is_teacher else "Student"
        print(f"{role} disconnected: user_id={self.user.id}, channel={self.channel_name}")

    async def receive(self, text_data):
        msg = json.loads(text_data)
        req_type  = msg.get("request_type")
        task_id   = msg.get("task_id")
        payload   = msg.get("data", {})
        receivers = msg.get("receivers", "all")
        sender_id = self.user.id

        # Студент не может отправлять произвольные списки — принудительно перенаправляем учителю
        if not self.is_teacher and (receivers == "teacher" or isinstance(receivers, list)):
            receivers = "teacher"

        if receivers == "all":
            await self.channel_layer.group_send(
                self.class_group,
                {
                    "type": "forward_message",
                    "request_type": req_type,
                    "task_id": task_id,
                    "data": payload,
                    "sender_id": sender_id,
                    "sender_channel": self.channel_name,
                }
            )
            return

        if receivers == "teacher":
            teacher_ids = await self._get_teacher_ids()
            for tid in teacher_ids:
                await self.channel_layer.group_send(
                    f"user_{tid}",
                    {
                        "type": "forward_message",
                        "request_type": req_type,
                        "task_id": task_id,
                        "data": payload,
                        "sender_id": sender_id,
                        "sender_channel": self.channel_name,
                    }
                )
            return

        if isinstance(receivers, list):
            for sid in receivers:
                await self.channel_layer.group_send(
                    f"user_{sid}",
                    {
                        "type": "forward_message",
                        "request_type": req_type,
                        "task_id": task_id,
                        "data": payload,
                        "sender_id": sender_id,
                        "sender_channel": self.channel_name,
                    }
                )
            return

        await self.send(text_data=json.dumps({
            "error": "Unknown receivers parameter",
            "receivers": receivers,
        }))

    async def forward_message(self, event):
        is_sender = event.get("sender_channel") == self.channel_name or event.get("sender_id") == self.user.id
        if is_sender:
            # Не отправлять сообщение обратно отправителю
            return

        await self.send(text_data=json.dumps({
            "request_type": event["request_type"],
            "task_id": event["task_id"],
            "data": event["data"],
            "sender_id": event["sender_id"],
        }))

    @database_sync_to_async
    def _is_teacher(self):
        from .models import Classroom
        cls = Classroom.objects.get(id=self.classroom_id)
        return self.user.id in cls.teachers.values_list("id", flat=True)

    @database_sync_to_async
    def _get_teacher_ids(self):
        from .models import Classroom
        cls = Classroom.objects.get(id=self.classroom_id)
        return list(cls.teachers.values_list("id", flat=True))
