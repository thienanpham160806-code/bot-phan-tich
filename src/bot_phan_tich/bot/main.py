"""Diem khoi chay bot.

Nguyen tac quan trong cho tieu chi "Tinh hoan thien (40%)": middleware bat MOI
ngoai le o tang ngoai cung. Bot khong bao gio duoc sap vi mot lenh sai cu phap,
mot ma khong ton tai hay mot loi mang.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, CallbackQuery, Message, TelegramObject

from ..alerts.eod import run_eod_scan
from ..analysis.snapshot import ensure_fresh_in_background, update_market_data
from ..config import auto_subscribe_chat_ids, get_secrets
from ..data.cache import (
    get_news_subscribers,
    init_db,
    save_macro_news_items,
    seed_subscribers,
)
from ..data.macro_news import fetch_all_macro_news, select_broadcast_items
from ..logging_conf import get_logger, setup_logging
from .formatters import error_card, macro_news_card
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


class AutoSubscribeNews(BaseMiddleware):
    """Chat nao nhan tin cho bot (bat ky lenh nao) duoc TU BAT ban tin tin tuc,
    tru khi da tung /tintuc off. Render Free xoa CSDL moi lan khoi dong lai,
    lam mat danh sach /tintuc on - nho middleware nay, dang ky tu phuc hoi
    ngay lan dau nguoi dung nhan tin sau khi restart, khong can bien moi
    truong. `_seen`: moi chat chi ghi CSDL mot lan cho moi lan bot chay."""

    def __init__(self) -> None:
        self._seen: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message is not None:
            chat = event.message.chat
        if chat is not None and chat.id not in self._seen:
            self._seen.add(chat.id)
            try:
                # INSERT OR IGNORE: khong ghi de lua chon /tintuc off da co.
                await asyncio.to_thread(seed_subscribers, [chat.id])
            except Exception as exc:  # noqa: BLE001 - khong duoc chan lenh cua nguoi dung
                log.warning("Khong tu dang ky tin tuc cho chat %s: %s", chat.id, exc)
        return await handler(event, data)


async def daily_scan_job(bot: Bot) -> None:
    """Cong viec cuoi phien, chay theo `bot.scan_cron` (xem bot/scheduler.py):

      1. Cap nhat kho gia + dung lai snapshot (analysis.snapshot.
         update_market_data - cung luong voi luc khoi dong, co khoa chong
         chay chong, ghi trang thai/loi cho /trangthai).
      2. Quet canh bao (alerts.eod.run_eod_scan()) va gui gop cho tung chat.

    Moi buoc nang CHAY TRONG THREAD RIENG (asyncio.to_thread), khong chan
    event loop cua bot.
    """
    # force=True: 15h05 van truoc moc 15h10 cua is_stale(), nen snapshot hom
    # qua chua bi coi la cu - nhung phien hom nay da dong, phai tinh lai.
    await update_market_data(force=True)

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


async def midday_update_job() -> None:
    """Sau phien sang (bot.midday_cron): tai nen DANG CHAY cua hom nay cho ca
    kho roi tinh lai snapshot - /loc, /tinhieu co gia phien sang (ghi chu
    "tam tinh", xem analysis/snapshot.py:intraday_note). 15h05 lich cuoi
    phien tai lai, nen dong cua ghi de nen tam (kho giu ban ghi moi hon).
    Khong gui canh bao: canh bao chi dua tren nen da dong cua."""
    await update_market_data(force=True)


async def hourly_news_job(bot: Bot) -> None:
    """Tong hop tin tuc vi mo, phap luat va phat song moi gio cho nguoi dung."""
    try:
        raw_items = await asyncio.to_thread(fetch_all_macro_news)
        dict_items = [it.to_dict() for it in raw_items]
        new_items = await asyncio.to_thread(save_macro_news_items, dict_items)
        log.info(
            "hourly_news_job: quet %d tin tu RSS, phat hien %d tin moi",
            len(dict_items),
            len(new_items),
        )

        # Chi gui tin dang trong 2 gio gan nhat (xem select_broadcast_items)
        fresh_items = select_broadcast_items(new_items)
        subscribers = await asyncio.to_thread(get_news_subscribers)
        if not subscribers or not fresh_items:
            return

        notice_card = macro_news_card(fresh_items[:5], title_suffix="1 Giờ Qua")
        for chat_id in subscribers:
            try:
                await bot.send_message(chat_id, notice_card)
            except Exception as exc:
                log.warning("Khong gui duoc ban tin cho chat %s: %s", chat_id, exc)
    except Exception:
        log.exception("hourly_news_job that bai")


async def run() -> None:
    setup_logging("logs/bot.log")
    init_db()
    # Render Free xoa CSDL moi lan khoi dong lai: dang ky san ban tin cho
    # cac chat trong AUTO_SUBSCRIBE_CHAT_IDS (khong ghi de lua chon da co).
    seed_subscribers(auto_subscribe_chat_ids())

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
    auto_subscribe = AutoSubscribeNews()
    dispatcher.message.outer_middleware(auto_subscribe)
    dispatcher.callback_query.outer_middleware(auto_subscribe)
    for router in ROUTERS:
        dispatcher.include_router(router)

    scheduler = build_scheduler(
        lambda: daily_scan_job(bot),
        lambda: hourly_news_job(bot),
        midday_update_job,
    )
    scheduler.start()

    # Neu snapshot thieu/cu luc khoi dong: cap nhat o NEN, khong cho bot
    # khoi dong - /loc va /tinhieu tu bao "dang chuan bi du lieu" trong
    # luc nay (xem analysis/snapshot.py:is_build_in_progress()).
    asyncio.create_task(ensure_fresh_in_background())

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="kn", description="Khuyến nghị & kế hoạch giá (VD: /kn FPT)"),
                BotCommand(command="chart", description="Biểu đồ nến kỹ thuật (VD: /chart SSI)"),
                BotCommand(command="info", description="Hồ sơ & định giá P/E, P/B (VD: /info VNM)"),
                BotCommand(command="fin", description="Đọc BCTC & rủi ro nợ vay (VD: /fin HPG)"),
                BotCommand(command="loc", description="Bộ lọc cổ phiếu toàn sàn (Breakout, Nền)"),
                BotCommand(command="tinhieu", description="Tín hiệu MUA / BÁN phiên gần nhất"),
                BotCommand(command="market", description="Trạng thái chỉ số thị trường VN-Index"),
                BotCommand(command="tintuc", description="Bản tin thị trường & nghị định/luật"),
                BotCommand(command="sub", description="Thêm vào danh mục theo dõi (VD: /sub FPT)"),
                BotCommand(command="watchlist", description="Xem danh sách cổ phiếu theo dõi"),
                BotCommand(command="canhbao", description="Bật/tắt cảnh báo tự động cuối phiên"),
                BotCommand(command="trangthai", description="Tình trạng dữ liệu & tiến độ nạp"),
                BotCommand(command="help", description="Hướng dẫn sử dụng chi tiết"),
            ]
        )
    except Exception as exc:
        log.warning("Khong the cai dat bot commands menu: %s", exc)

    log.info("Bot bat dau chay")

    # BAT BUOC khi deploy tren goi Free cua Render (render.yaml: type: web) -
    # goi Free KHONG ho tro Background Worker ("service type is not
    # available for this plan", da gap thuc te), nen phai deploy nhu Web
    # Service va tu mo mot port gia de qua vong quet port cua Render. Neu
    # sau nay nang cap len goi tra phi va doi sang type: worker, khoi nay tu
    # vo hai (bien PORT se khong duoc dat, "if port_str" khong chay).
    # Xem README.md muc 7.3 (gom ca cach giu bot khong bi Render "ngu" do
    # goi Free spin-down sau ~15 phut khong co request HTTP - can UptimeRobot
    # ping dinh ky vao /healthz).
    port_str = os.getenv("PORT")
    web_runner = None
    if port_str:
        try:
            from aiohttp import web

            app = web.Application()

            async def _health_handler(_request: web.Request) -> web.Response:
                return web.Response(text="Bot is running!")

            app.router.add_get("/", _health_handler)
            app.router.add_get("/healthz", _health_handler)

            web_runner = web.AppRunner(app)
            await web_runner.setup()
            site = web.TCPSite(web_runner, "0.0.0.0", int(port_str))
            await site.start()
            log.info("Da khoi dong health check server tai port %s (Render/Cloud)", port_str)
        except Exception as exc:
            log.warning("Khong the khoi dong health check tren port %s: %s", port_str, exc)

    try:
        await dispatcher.start_polling(bot)
    finally:
        if web_runner:
            await web_runner.cleanup()
        scheduler.shutdown(wait=False)
        await bot.session.close()



def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit) as exc:
        log.info("Dung bot: %s", exc)


if __name__ == "__main__":
    main()
