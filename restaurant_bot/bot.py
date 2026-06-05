from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent
from aiogram.types import MenuButtonWebApp, WebAppInfo

from restaurant_bot.config import load_settings
from restaurant_bot.database import init_db
from restaurant_bot.handlers import admin, customer, staff


async def on_error(event: ErrorEvent) -> None:
    logging.exception("Unhandled bot error: %s", event.exception)
    update = event.update
    message = getattr(update, "message", None)
    callback = getattr(update, "callback_query", None)
    try:
        if callback:
            await callback.answer("Something went wrong. Please try again.", show_alert=True)
        elif message:
            await message.answer("Something went wrong. Please try again.")
    except TelegramAPIError:
        logging.exception("Failed to notify user about error.")


async def configure_bot_commands(bot: Bot, admin_ids: set[int]) -> None:
    customer_commands = [
        BotCommand(command="start", description="Start / choose language"),
        BotCommand(command="menu", description="Browse menu"),
        BotCommand(command="cart", description="My order"),
        BotCommand(command="orders", description="My orders"),
        BotCommand(command="reorder", description="Reorder last delivered order"),
        BotCommand(command="rewards", description="Rewards balance"),
        BotCommand(command="contact", description="Contact restaurant"),
        BotCommand(command="language", description="Change language"),
    ]
    admin_commands = [
        *customer_commands,
        BotCommand(command="admin", description="Admin dashboard"),
        BotCommand(command="demo_reset", description="Admin: reset demo orders/carts"),
    ]
    await bot.set_my_commands(customer_commands)
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError:
            logging.warning("Could not set admin command menu for admin chat %s.", admin_id, exc_info=True)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await configure_bot_commands(bot, settings.admin_ids)
    if settings.miniapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🍽 Open Menu", web_app=WebAppInfo(url=settings.miniapp_url)))
    dp = Dispatcher(storage=MemoryStorage(), settings=settings)
    dp.include_router(admin.router)
    dp.include_router(staff.router)
    dp.include_router(customer.router)
    dp.errors.register(on_error)

    logging.info("Starting bot polling.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
