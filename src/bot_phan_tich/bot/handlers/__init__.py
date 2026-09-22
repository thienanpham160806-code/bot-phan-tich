"""Cac nhom lenh cua bot."""

from . import common, finreport, lookup, recommend, screener, signals, watchlist

ROUTERS = [
    common.router,
    lookup.router,
    recommend.router,
    screener.router,
    signals.router,
    finreport.router,
    watchlist.router,
]

__all__ = ["ROUTERS"]
