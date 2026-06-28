from pathlib import Path

from insider_swing_trader.cli import main


def test_sec_live_with_no_events_does_not_reference_unloaded_congress(tmp_path):
    earnings = tmp_path / "earnings.csv"
    earnings.write_text("ticker,earnings_date,timing,previous_earnings_date\n")
    market = tmp_path / "market.csv"
    market.write_text("ticker,last_price,average_volume\n")

    code = main(
        [
            "scan",
            "--earnings-csv",
            str(earnings),
            "--market-csv",
            str(market),
            "--sec-live",
            "--start",
            "2026-06-01",
            "--end",
            "2026-06-30",
            "--db-path",
            str(tmp_path / "scan.sqlite3"),
        ]
    )

    assert code == 0


def test_dry_run_exit_uses_recorded_order_ledger(tmp_path, capsys):
    db_path = tmp_path / "orders.sqlite3"
    main(
        [
            "paper-trade",
            "--earnings-csv",
            "examples/earnings.csv",
            "--insider-xml-dir",
            "examples/form4",
            "--market-csv",
            "examples/market.csv",
            "--congress-csv",
            "examples/congress.csv",
            "--decision-at",
            "2026-06-20T16:00:00",
            "--db-path",
            str(db_path),
            "--dry-run",
        ]
    )

    code = main(
        [
            "paper-trade",
            "--earnings-csv",
            "examples/earnings.csv",
            "--market-csv",
            "examples/market.csv",
            "--order-side",
            "exit",
            "--ticker",
            "EXMP",
            "--db-path",
            str(db_path),
            "--dry-run",
        ]
    )

    assert code == 0
    assert "DRY RUN SELL 950 EXMP" in capsys.readouterr().out


def test_run_cycle_enters_due_candidate_then_exits_due_position(tmp_path, capsys):
    db_path = tmp_path / "cycle.sqlite3"
    entry_code = main(
        [
            "run-cycle",
            "--earnings-csv",
            "examples/earnings.csv",
            "--insider-xml-dir",
            "examples/form4",
            "--market-csv",
            "examples/market.csv",
            "--congress-csv",
            "examples/congress.csv",
            "--decision-at",
            "2026-06-30T15:45:00",
            "--as-of",
            "2026-06-30T15:45:00",
            "--db-path",
            str(db_path),
            "--dry-run",
        ]
    )

    assert entry_code == 0
    assert "DRY RUN ENTRY EXMP quantity=950" in capsys.readouterr().out

    exit_code = main(
        [
            "run-cycle",
            "--earnings-csv",
            "examples/earnings.csv",
            "--market-csv",
            "examples/market.csv",
            "--as-of",
            "2026-07-01T15:45:00",
            "--db-path",
            str(db_path),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "DRY RUN EXIT EXMP quantity=950" in output
