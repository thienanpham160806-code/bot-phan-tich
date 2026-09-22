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
from ..analysis.snapshot import build_snapshot, ensure_fresh_in_background
from ..config import get_secrets
from ..data import market_store
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
    """Cong viec cuoi phien, chay theo `bot.scan_cron` (xem bot/scheduler.py):

      1. Cap nhat tang dan kho gia toan san (market_store.refresh()).
      2. Dung lai snapshot khuyen nghi (analysis.snapshot.build_snapshot()) -
         de /loc va /tinhieu tra ket qua ngay lap tuc, khong tinh lai.
      3. Quet canh bao (alerts.eod.run_eod_scan()) va gui gop cho tung chat.

    Ca 3 buoc deu CHAY TRONG THREAD RIENG (asyncio.to_thread) - day la cong
    viec nang (I/O mang + tinh CPU tren toan vu tru), khong duoc chan event
    loop cua bot trong luc chay, neu khong bot se "dung hinh" ca budi.
    """
    try:
        updated_rows = await asyncio.to_thread(market_store.refresh)
        log.info("daily_scan_job: market_store.refresh() -> %d dong", updated_rows)
        snapshot_frame = await asyncio.to_thread(build_snapshot)
        log.info("daily_scan_job: build_snapshot() -> %d ma", len(snapshot_frame))
    except Exception:
        log.exception("daily_scan_job: cap nhat kho/snapshot that bai")

    try:
        alerts = await asyncio.to_thread(run_eod_scan)
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

    # Neu snapshot thieu/cu luc khoi dong: cap nhat o NEN, khong cho bot
    # khoi dong - /loc va /tinhieu tu bao "dang chuan bi du lieu" trong
    # luc nay (xem analysis/snapshot.py:is_build_in_progress()).
    asyncio.create_task(ensure_fresh_in_background())

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
