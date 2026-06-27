from datetime import date

from isem_trader.config import StrategyConfig
from isem_trader.models import EarningsEvent, EarningsTiming, InsiderTransaction, SignalWindow
from isem_trader.scoring import classify_window, score_candidate


def test_classify_windows():
    config = StrategyConfig()
    prior = date(2026, 3, 28)
    next_earnings = date(2026, 6, 29)

    assert classify_window(date(2026, 4, 5), prior, next_earnings, config) == SignalWindow.EXCLUDED
    assert classify_window(date(2026, 5, 1), prior, next_earnings, config) == SignalWindow.CORE
    assert classify_window(date(2026, 6, 10), prior, next_earnings, config) == SignalWindow.LATE
    assert classify_window(date(2026, 6, 27), prior, next_earnings, config) == SignalWindow.FINAL


def test_score_candidate_matches_proposal_dimensions():
    config = StrategyConfig()
    event = EarningsEvent("ACME", date(2026, 6, 29), EarningsTiming.BMO, "NASDAQ")
    prior = date(2026, 3, 28)
    txs = [
        InsiderTransaction("ACME", "1", "Jane CEO", "CEO", "corporate", date(2026, 5, 20), 10_000, 20.0),
        InsiderTransaction("ACME", "2", "Pat Director", "Director", "corporate", date(2026, 6, 8), 8_000, 22.0),
        InsiderTransaction(
            "ACME",
            "3",
            "Rep Buyer",
            "Congress",
            "congress",
            date(2026, 6, 10),
            5_000,
            21.0,
            disclosed_date=date(2026, 6, 24),
        ),
        InsiderTransaction("ACME", "4", "Planned", "CFO", "corporate", date(2026, 6, 11), 99_000, 30.0, True),
    ]

    score = score_candidate(event, prior, txs, date(2026, 6, 26), config)

    assert score.score == 80
    assert score.breakdown.insider_count == 15
    assert score.breakdown.role_weighting == 20
    assert score.breakdown.timing_quality == 20
    assert score.breakdown.velocity == 20
    assert score.breakdown.congress_lag_adjustment == 5
    assert len(score.transactions) == 3
