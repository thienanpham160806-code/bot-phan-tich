"""Chay thu mot lan quet EOD, in ket qua ra console (khong can Telegram).

Dung de kiem tra logic canh bao truoc khi noi vao bot/scheduler.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot_phan_tich.alerts.eod import run_eod_scan  # noqa: E402
from bot_phan_tich.logging_conf import setup_logging  # noqa: E402


def main() -> None:
    setup_logging()
    alerts = run_eod_scan()

    print("\n" + "=" * 70)
    if not alerts:
        print("Khong co thay doi dang chu y cho bat ky ma nao dang theo doi.")
    else:
        print(f"Co {len(alerts)} chat can gui canh bao:\n")
        for alert in alerts:
            print(f"--- chat_id {alert.chat_id} ---")
            print("\n".join(alert.lines))
            print()
    print("=" * 70)


if __name__ == "__main__":
    main()
