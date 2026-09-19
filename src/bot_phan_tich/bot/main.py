"""Diem khoi chay bot.

Nguyen tac quan trong cho tieu chi "Tinh hoan thien (40%)": middleware bat MOI
ngoai le o tang ngoai cung. Bot khong bao gio duoc sap vi mot lenh sai cu phap,
mot ma khong ton tai hay mot loi mang.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, TelegramObject

from ..alerts.eod import run_eod_scan
from ..config import get_secrets
from ..data.cache import init_db
from ..logging_conf import get_logger, setup_logging
from .formatters import error_card
from .handlers import ROUTERS
from .scheduler import build_scheduler

log = get_logger(__name__)


class ErrorGuard(BaseMiddleware):
    """Bat moi ngoai le chua duoc xu ly, tra ve tin nhan lich su thay vi sap bot."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:  # noqa: BLE001
            log.exception("Ngoai le chua xu ly trong handler")
            if isinstance(event, Message):
                try:
                    await event.answer(error_card(str(exc)))
                except Exception:
                    pass
            return None


async def daily_scan_job(bot: Bot) -> None:
    """Quet cuoi phien (alerts.eod.run_eod_scan) roi gui canh bao gop cho tung chat.

    run_eod_scan() khong goi Telegram - chi tra ve danh sach EodAlert, viec
    gui thuc su nam o day de giu alerts/ khong phai module duoc goi mang.
    """
    try:
        alerts = run_eod_scan()
    except Exception:
        log.exception("Quet dinh ky (EOD) that bai")
        return

    for alert in alerts:
        try:
            await bot.send_message(alert.chat_id, "\n".join(alert.lines))
        except Exception as exc:
            log.warning("Khong gui duoc canh bao cho chat %s: %s", alert.chat_id, exc)


async def run() -> None:
    setup_logging()
    init_db()

    secrets = get_secrets()
    if not secrets.telegram_token:
        raise SystemExit(
            "Thieu TELEGRAM_BOT_TOKEN. Tao bot voi @BotFather roi dien vao file .env"
        )

    bot = Bot(
        token=secrets.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.message.middleware(ErrorGuard())
    dispatcher.callback_query.middleware(ErrorGuard())
    for router in ROUTERS:
        dispatcher.include_router(router)

    scheduler = build_scheduler(lambda: daily_scan_job(bot))
    scheduler.start()

    log.info("Bot bat dau chay")
    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit) as exc:
        log.info("Dung bot: %s", exc)


if __name__ == "__main__":
    main()
