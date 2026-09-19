"""Chi so hieu nang. Moi con so deu da tru phi va thue."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def total_return(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def cagr(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    if len(equity) < 2:
        return 0.0
    years = len(equity) / periods_per_year
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0


def max_drawdown(equity: pd.Series) -> float:
    """Muc giam sau nhat tu dinh duong von. Quan trong hon loi nhuan:
    no quyet dinh nguoi dung co du suc giu chien luoc hay khong."""
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float((equity / peak - 1).min())


def sharpe(
    returns: pd.Series, risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    if returns.empty or returns.std(ddof=0) == 0:
        return 0.0
    excess = returns - risk_free / periods_per_year
    return float(excess.mean() / excess.std(ddof=0) * np.sqrt(periods_per_year))


def deflated_sharpe(observed: float, n_trials: int, n_obs: int) -> float:
    """Sharpe hieu chinh theo so lan thu tham so.

    Thu 1000 to hop roi bao cao to hop dep nhat la cach de nhat de tu lua. Chi so
    nay tru bot phan "may man do tim kiem nhieu".
    """
    if n_trials <= 1 or n_obs <= 1:
        return observed
    euler = 0.5772156649
    expected_max = (1 - euler) * _z(1 - 1 / n_trials) + euler * _z(1 - 1 / (n_trials * np.e))
    return float(observed - expected_max / np.sqrt(n_obs))


def _z(p: float) -> float:
    from scipy.stats import norm  # type: ignore

    return float(norm.ppf(min(max(p, 1e-9), 1 - 1e-9)))


def profit_factor(trade_returns: pd.Series) -> float:
    gains = trade_returns[trade_returns > 0].sum()
    losses = abs(trade_returns[trade_returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def win_rate(trade_returns: pd.Series) -> float:
    return float((trade_returns > 0).mean()) if len(trade_returns) else 0.0


def expectancy_r(r_multiples: pd.Series) -> float:
    """Ky vong moi lenh tinh bang boi so R - chi so trung thuc nhat."""
    return float(r_multiples.mean()) if len(r_multiples) else 0.0


def summarise(equity: pd.Series, trades: pd.DataFrame) -> dict:
    returns = equity.pct_change().dropna()
    trade_returns = trades["return"] if "return" in trades.columns else pd.Series(dtype=float)
    r_values = trades["r_multiple"] if "r_multiple" in trades.columns else pd.Series(dtype=float)

    return {
        "Ti suat sinh loi tich luy": total_return(equity),
        "CAGR": cagr(equity),
        "Sut giam toi da": max_drawdown(equity),
        "Ti so Sharpe": sharpe(returns),
        "He so loi nhuan": profit_factor(trade_returns),
        "Ti le thang": win_rate(trade_returns),
        "Ky vong (boi so R)": expectancy_r(r_values),
        "So lenh": int(len(trades)),
    }


def format_report(stats: dict) -> str:
    lines = []
    for key, value in stats.items():
        if isinstance(value, float):
            if key in {"So lenh"}:
                lines.append(f"{key}: {int(value)}")
            elif "R)" in key or "He so" in key or "Sharpe" in key:
                lines.append(f"{key}: {value:.2f}")
            else:
                lines.append(f"{key}: {value:.2%}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
