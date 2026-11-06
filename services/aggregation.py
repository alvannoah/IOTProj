"""Shared helpers for turning raw readings into usage figures and graph buckets."""
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement

from config.settings import settings

INTERVAL_SECONDS = {"minute": 60, "hour": 3600, "day": 86400}


def counter_delta(previous: float | None, current: float) -> float:
    """Usage since the last reading, from a running total.

    The first reading counts as zero: a meter may already hold a large lifetime
    total, which must not be billed as one reading. If the total goes backwards
    the counter was reset (e.g. the Arduino rebooted), so it counted up from zero.
    """
    if previous is None:
        return 0.0
    return current - previous if current >= previous else current


def local_tz() -> timezone:
    return timezone(timedelta(minutes=settings.utc_offset_minutes))


def as_utc(value: datetime) -> datetime:
    """Normalise a datetime to aware UTC; naive values are taken to be UTC already."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class epoch_seconds(FunctionElement):
    """Seconds since 1970 for a stored UTC column, independent of the DB session timezone."""

    type = BigInteger()
    inherit_cache = True


@compiles(epoch_seconds, "mysql")
def _epoch_mysql(element, compiler, **kw):
    return f"TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', {compiler.process(element.clauses, **kw)})"


@compiles(epoch_seconds, "sqlite")
def _epoch_sqlite(element, compiler, **kw):
    return f"CAST(strftime('%s', {compiler.process(element.clauses, **kw)}) AS INTEGER)"


def bucket_column(column, interval: str):
    """SQL expression for the local-time bucket a row falls in, so days start at local midnight."""
    size = INTERVAL_SECONDS[interval]
    shifted = epoch_seconds(column) + settings.utc_offset_minutes * 60
    return (shifted - shifted % size).label("bucket")


def bucket_start(bucket_value) -> datetime:
    """Convert a value from bucket_column back into a UTC datetime."""
    return datetime.fromtimestamp(int(bucket_value) - settings.utc_offset_minutes * 60, UTC)
