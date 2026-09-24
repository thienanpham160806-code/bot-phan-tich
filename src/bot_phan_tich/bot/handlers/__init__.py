"""Cac nhom lenh cua bot."""

from . import (
    common,
    finreport,
    lookup,
    news,
    pulse,
    recommend,
    screener,
    signals,
    status,
    watchlist,
)

ROUTERS = [
    common.router,
    news.router,
    pulse.router,
    lookup.router,
    recommend.router,
    screener.router,
    signals.router,
    finreport.router,
    watchlist.router,
    status.router,
]

__all__ = ["ROUTERS"]

