"""Lich quet cuoi phien va day canh bao theo watchlist."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..logging_conf import get_logger

log = get_logger(__name__)


def build_scheduler(scan_callback) -> AsyncIOScheduler:
    """scan_callback: coroutine khong tham so, chay moi phien sau gio dong cua."""
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
    log.info("Da dat lich quet: '%s' (%s)", cron, timezone)
    return scheduler
