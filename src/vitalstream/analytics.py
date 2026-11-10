from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median

from vitalstream.schemas import Insight


def baseline_insight(samples: list[tuple[datetime, float]], source: str, now: datetime) -> Insight:
    """Descriptive baseline only; a robust score is not an illness probability."""
    start = now - timedelta(days=28)
    days: dict = defaultdict(list)
    for timestamp, value in samples:
        timestamp = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
        if start <= timestamp <= now:
            days[timestamp.astimezone(UTC).date()].append(value)
    common = dict(source=source, window_start=start, generated_at=now)
    if not days:
        return Insight(
            status="insufficient_data", explanation="No readings in the last 28 days.", **common
        )
    latest_day = max(days)
    latest = float(median(days[latest_day]))
    history = [float(median(values)) for day, values in sorted(days.items()) if day < latest_day]
    if len(history) < 7:
        return Insight(
            status="insufficient_data",
            latest_value=latest,
            history_days=len(history),
            explanation="At least 7 earlier days are needed for a baseline.",
            **common,
        )
    reference = float(median(history))
    mad = float(median(abs(value - reference) for value in history))
    delta = latest - reference
    # A zero MAD cannot produce a meaningful standardized score. Keep the raw deviation.
    score = round(delta / (1.4826 * mad), 2) if mad > 0 else None
    stale = (now.astimezone(UTC).date() - latest_day).days > 2
    # JOSEPH-M3 (intermediate): add a candidate anomaly model behind this same input/output
    # boundary. Build daily features, split chronologically BEFORE fitting/scaling, and compare
    # false-alert rates against this baseline on held-out data. Keep synthetic scenarios for
    # regression tests, not medical accuracy claims. Never train on the scored day's future.
    return Insight(
        status="stale" if stale else "ready",
        latest_value=latest,
        baseline=reference,
        deviation=round(delta, 2),
        robust_score=score,
        history_days=len(history),
        explanation=("Latest reading is over two days old. " if stale else "")
        + f"Latest daily median differs from your earlier baseline by {delta:+.1f} bpm. "
        + "This describes a trend, not a diagnosis. Days are grouped in UTC.",
        **common,
    )
