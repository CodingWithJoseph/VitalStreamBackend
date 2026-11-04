from datetime import UTC, datetime, timedelta

from vitalstream.analytics import baseline_insight


def test_coverage_zero_dispersion_staleness_and_no_future_leakage():
    now = datetime(2026, 11, 1, tzinfo=UTC)
    samples = [(now - timedelta(days=i), 60.0) for i in range(3, 12)]
    result = baseline_insight(samples, "synthetic", now)
    assert result.status == "stale"
    assert result.robust_score is None
    assert result.deviation == 0
    assert baseline_insight(samples + [(now + timedelta(days=1), 200)], "synthetic", now) == result
    assert baseline_insight(samples[:3], "synthetic", now).status == "insufficient_data"


def test_multiple_readings_do_not_inflate_history_days():
    now = datetime.now(UTC)
    samples = [(now - timedelta(days=1), 60.0)] * 100
    result = baseline_insight(samples, "synthetic", now)
    assert result.status == "insufficient_data"
    assert result.history_days == 0
