"""``BirthDateTime`` — typed builder + validator for the (date, time, lat, lon, tz)
tuple every chart-style endpoint takes. Reduces boilerplate when constructing
request bodies and catches malformed input before the network round-trip.

Example::

    from astroway import Astroway
    from astroway.helpers import BirthDateTime

    aw = Astroway(api_key="aw_live_...")

    birth = BirthDateTime.from_coordinates(
        date="1990-07-14", time="14:30:00",
        latitude=50.45, longitude=30.52, timezone_offset=3,
    )
    chart = aw.chart.compute(birth.to_body())
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)")


@dataclass(frozen=True)
class BirthDateTime:
    """Immutable container for a birth-moment input."""

    date: str
    time: str
    timezone_offset: float = 0
    latitude: float = 0
    longitude: float = 0

    def __post_init__(self) -> None:
        if not _DATE_RE.match(self.date):
            raise ValueError(f"BirthDateTime: date must be YYYY-MM-DD, got {self.date!r}")
        if not _TIME_RE.match(self.time):
            raise ValueError(f"BirthDateTime: time must be HH:MM:SS, got {self.time!r}")

    @classmethod
    def from_coordinates(
        cls,
        *,
        date: str,
        time: str,
        latitude: float = 0,
        longitude: float = 0,
        timezone_offset: float = 0,
    ) -> BirthDateTime:
        """Explicit canonical construction with eager format validation."""
        return cls(
            date=date,
            time=time,
            timezone_offset=timezone_offset,
            latitude=latitude,
            longitude=longitude,
        )

    @classmethod
    def from_datetime(
        cls,
        moment: datetime,
        *,
        latitude: float = 0,
        longitude: float = 0,
        timezone_offset: float = 0,
    ) -> BirthDateTime:
        """From a stdlib ``datetime``. The instance is split into ``YYYY-MM-DD`` +
        ``HH:MM:SS`` using its UTC components — pass a tzinfo-aware datetime in the
        birth-place local time, or a naive one (treated as already local)."""
        if moment.tzinfo is not None:
            moment = moment.astimezone(timezone.utc)
        return cls.from_coordinates(
            date=moment.strftime("%Y-%m-%d"),
            time=moment.strftime("%H:%M:%S"),
            latitude=latitude,
            longitude=longitude,
            timezone_offset=timezone_offset,
        )

    @classmethod
    def parse(
        cls,
        iso: str,
        *,
        latitude: float = 0,
        longitude: float = 0,
        timezone_offset: float = 0,
    ) -> BirthDateTime:
        """From a full ISO 8601 string like ``1990-07-14T14:30:00``. Trailing
        ``Z`` / ``+HH:MM`` is stripped — the API tracks ``timezone_offset`` separately."""
        match = _ISO_RE.match(iso)
        if not match:
            raise ValueError(f"BirthDateTime: cannot parse ISO datetime {iso!r}")
        date_part, time_part = match.group(1), match.group(2)
        if len(time_part) == 5:
            time_part += ":00"
        return cls.from_coordinates(
            date=date_part,
            time=time_part,
            latitude=latitude,
            longitude=longitude,
            timezone_offset=timezone_offset,
        )

    def to_body(self) -> dict[str, Any]:
        """Wire shape for ``aw.chart.compute(birth.to_body())`` etc."""
        return {
            "date": self.date,
            "time": self.time,
            "timezoneOffset": self.timezone_offset,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    def to_datetime(self) -> datetime:
        """Return a tz-aware UTC ``datetime`` (deterministic, drops timezone_offset)."""
        return datetime.strptime(
            f"{self.date} {self.time}", "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
