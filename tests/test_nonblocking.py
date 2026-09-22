"""Chung minh: trong luc mot lenh NANG dang chay (vi du /tracuu goi mang/tinh
chi bao mat vai giay), lenh NHE nhu /help van tra loi ngay lap tuc - vi moi
ham nang deu duoc boc bang await asyncio.to_thread(...) (xem PHAN 4).

Neu mot handler nao do lam mat wrapping nay (goi ham chan truc tiep trong
coroutine), test se ĐO ĐƯỢC /help bi tre vi phai cho lenh nang chay xong
truoc - do la dieu test nay phat hien.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from bot_phan_tich.bot.handlers import common as common_mod
from bot_phan_tich.bot.handlers import lookup as lookup_mod

_HEAVY_SECONDS = 0.5


class FakeMessage:
    """Gia lap aiogram.types.Message toi thieu du de chay handler."""

    def __init__(self, text: str):
        self.text = text
        self.answers: list[tuple[float, str]] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append((time.monotonic(), text))
        return self


def _blocking_lookup(symbol: str):
    """Gia lap mot ham nang CHAN THUC SU (time.sleep, khong await) - giong
    nhu goi mang that hoac tinh chi bao tren du lieu lon."""
    time.sleep(_HEAVY_SECONDS)
    return object()


@pytest.mark.asyncio
async def test_help_answers_immediately_while_heavy_command_runs(monkeypatch):
    monkeypatch.setattr(lookup_mod, "lookup", _blocking_lookup)
    monkeypatch.setattr(lookup_mod, "lookup_card", lambda profile: "ok")

    heavy_message = FakeMessage("/tracuu FPT")
    fast_message = FakeMessage("/help")

    started = time.monotonic()
    await asyncio.gather(
        lookup_mod.cmd_lookup(heavy_message),
        common_mod.cmd_help(fast_message),
    )

    assert fast_message.answers, "/help phai tra loi"
    assert heavy_message.answers, "/tracuu phai tra loi"

    fast_elapsed = fast_message.answers[0][0] - started
    heavy_elapsed = heavy_message.answers[0][0] - started

    # /help khong bi ham nang (time.sleep trong to_thread) chan lai - phai
    # xong RAT SOM, khong can cho het _HEAVY_SECONDS cua lenh /tracuu.
    assert fast_elapsed < _HEAVY_SECONDS / 2
    assert heavy_elapsed >= _HEAVY_SECONDS
