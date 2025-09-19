import asyncio
from bot import dp, bot
import handlers  # подключаем, чтобы хендлеры зарегистрировались

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
