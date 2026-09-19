from bot_phan_tich.risk.sizing import position_size, r_multiple


def test_risk_amount_respects_budget():
    size = position_size(capital=100_000_000, entry=50_000, stop_loss=47_000,
                         risk_per_trade=0.01)
    assert size.shares > 0
    assert size.shares % 100 == 0
    assert size.risk_amount <= 100_000_000 * 0.01 + 1e-6


def test_weight_cap_binds():
    size = position_size(capital=100_000_000, entry=50_000, stop_loss=49_900,
                         risk_per_trade=0.01, max_weight=0.15)
    assert size.weight <= 0.15 + 1e-9


def test_invalid_stop_returns_zero():
    assert position_size(100_000_000, 50_000, 50_000).shares == 0
    assert position_size(100_000_000, 50_000, 51_000).shares == 0


def test_bear_regime_blocks_entry():
    assert position_size(100_000_000, 50_000, 47_000, regime_multiplier=0.0).shares == 0


def test_r_multiple():
    assert abs(r_multiple(100, 130, 90) - 3.0) < 1e-9
