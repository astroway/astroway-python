"""BirthDateTime helper — factories + validation + serialization."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from astroway.helpers import BirthDateTime

# ─── from_coordinates ────────────────────────────────────────────


def test_from_coordinates_canonical_shape() -> None:
    b = BirthDateTime.from_coordinates(
        date="1990-07-14", time="14:30:00",
        latitude=50.45, longitude=30.52, timezone_offset=3,
    )
    assert b.date == "1990-07-14"
    assert b.time == "14:30:00"
    assert b.latitude == 50.45
    assert b.longitude == 30.52
    assert b.timezone_offset == 3


def test_from_coordinates_defaults_to_zero_geo() -> None:
    b = BirthDateTime.from_coordinates(date="1990-07-14", time="14:30:00")
    assert b.latitude == 0
    assert b.longitude == 0
    assert b.timezone_offset == 0


def test_from_coordinates_rejects_bad_date() -> None:
    with pytest.raises(ValueError):
        BirthDateTime.from_coordinates(date="not-a-date", time="14:30:00")


def test_from_coordinates_rejects_bad_time() -> None:
    with pytest.raises(ValueError):
        BirthDateTime.from_coordinates(date="1990-07-14", time="14:30")


# ─── from_datetime ───────────────────────────────────────────────


def test_from_datetime_naive() -> None:
    b = BirthDateTime.from_datetime(
        datetime(1990, 7, 14, 14, 30, 0),
        latitude=50.45, longitude=30.52, timezone_offset=3,
    )
    assert b.date == "1990-07-14"
    assert b.time == "14:30:00"
    assert b.timezone_offset == 3


def test_from_datetime_tz_aware_converts_to_utc() -> None:
    # tz-aware datetime: 14:30 UTC+3 → 11:30 UTC
    moment = datetime(1990, 7, 14, 14, 30, 0, tzinfo=timezone.utc)
    b = BirthDateTime.from_datetime(moment, latitude=50.45, longitude=30.52)
    assert b.date == "1990-07-14"
    assert b.time == "14:30:00"


# ─── parse ───────────────────────────────────────────────────────


def test_parse_full_iso() -> None:
    b = BirthDateTime.parse(
        "1990-07-14T14:30:00",
        latitude=50.45, longitude=30.52, timezone_offset=3,
    )
    assert b.date == "1990-07-14"
    assert b.time == "14:30:00"
    assert b.timezone_offset == 3


def test_parse_iso_without_seconds_pads_zero() -> None:
    b = BirthDateTime.parse("1990-07-14T14:30")
    assert b.time == "14:30:00"


def test_parse_strips_trailing_z() -> None:
    b = BirthDateTime.parse("1990-07-14T14:30:00Z")
    assert b.date == "1990-07-14"
    assert b.time == "14:30:00"


def test_parse_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        BirthDateTime.parse("not-an-iso")


# ─── to_body / to_datetime ───────────────────────────────────────


def test_to_body_returns_wire_shape() -> None:
    b = BirthDateTime.from_coordinates(
        date="1990-07-14", time="14:30:00",
        latitude=50.45, longitude=30.52, timezone_offset=3,
    )
    assert b.to_body() == {
        "date": "1990-07-14",
        "time": "14:30:00",
        "timezoneOffset": 3,
        "latitude": 50.45,
        "longitude": 30.52,
    }


def test_to_datetime_returns_utc_aware_datetime() -> None:
    b = BirthDateTime.from_coordinates(date="1990-07-14", time="14:30:00")
    dt = b.to_datetime()
    assert dt.year == 1990
    assert dt.month == 7
    assert dt.day == 14
    assert dt.hour == 14
    assert dt.tzinfo is not None


def test_immutability() -> None:
    b = BirthDateTime.from_coordinates(date="1990-07-14", time="14:30:00")
    with pytest.raises(AttributeError):  # frozen dataclass
        b.date = "2000-01-01"  # type: ignore[misc]
