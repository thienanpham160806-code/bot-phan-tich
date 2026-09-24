"""Lich quet cuoi phien va day canh bao theo watchlist."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..logging_conf import get_logger

log = get_logger(__name__)


def build_scheduler(scan_callback, news_callback=None, pulse_callback=None) -> AsyncIOScheduler:
    """scan_callback: coroutine chay cuoi phien (EOD).

    news_callback: coroutine tong hop tin tuc vi mo, phap luat va phat song moi gio.

    pulse_callback: coroutine gui ban tin bien dong thi truong trong phien
    (moi moc trong bot.market_pulse_crons).
    """
    settings = get_settings()
    cron = settings.get("bot.scan_cron", "5 15 * * 1-5")
    timezone = settings.get("bot.timezone", "Asia/Ho_Chi_Minh")

    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        scan_callback,
        CronTrigger.from_crontab(cron, timezone=timezone),
        id="daily_scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    log.info("Da dat lich quet tin hieu cuoi phien: '%s' (%s)", cron, timezone)

    if news_callback is not None:
        news_cron = settings.get("bot.news_cron", "0 8-22 * * *")
        scheduler.add_job(
            news_callback,
            CronTrigger.from_crontab(news_cron, timezone=timezone),
            id="hourly_news",
            replace_existing=True,
            misfire_grace_time=1800,
        )
        log.info("Da dat lich tong hop tin tuc vi mo: '%s' (%s)", news_cron, timezone)

    if pulse_callback is not None:
        crons = settings.get("bot.market_pulse_crons", ["35 11 * * 1-5", "50 14 * * 1-5"])
        for i, pulse_cron in enumerate(crons):
            scheduler.add_job(
                pulse_callback,
                CronTrigger.from_crontab(pulse_cron, timezone=timezone),
                id=f"market_pulse_{i}",
                replace_existing=True,
                misfire_grace_time=600,
            )
        log.info("Da dat lich ban tin bien dong thi truong: %s (%s)", crons, timezone)

    return scheduler

