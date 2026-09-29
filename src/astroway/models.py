"""Pydantic v2 request models for the top-4 endpoint categories.

These provide IDE autocomplete + validation at the call site for the most
common workflows (natal charts, synastry, transits, Vedic dashas). The
remaining 90+ namespaces accept dict bodies until coverage expands in a4-a5.

Both `dict` and Pydantic input are accepted everywhere — `request()` calls
`.model_dump()` automatically when given a `BaseModel`. Use whichever feels
more natural for your code.

Example::

    from astroway import Astroway
    from astroway.models import BirthData

    aw = Astroway(api_key="aw_live_...")

    birth = BirthData(
        date="1990-07-14", time="14:30:00",
        timezone="Europe/Kyiv", latitude=50.45, longitude=30.52,
    )
    chart = aw.chart.compute(birth)        # accepts BirthData or dict
    transits = aw.transits.compute(TransitsRequest(
        date="1990-07-14", time="14:30:00", timezone="Europe/Kyiv",
        latitude=50.45, longitude=30.52, transit_date="2027-01-01",
    ))
"""

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# All API field names are camelCase. Pydantic v2 picks them up via `alias` +
# `populate_by_name`, so users can write either `timezone_offset=3` (Python
# style) or `timezoneOffset=3` (matching the JSON wire format).
_API_CONFIG = ConfigDict(populate_by_name=True, extra="allow")

# "+03:00", "-5" and "UTC+2" are offsets, and the API answers 400 for each of
# them in the `timezone` field. Catching them here saves the round trip.
_OFFSET_LIKE = re.compile(r"^(?:UTC|GMT)?\s*[+-]?\d{1,2}(?::\d{2})?$", re.IGNORECASE)


def _check_timezone(value: Optional[str]) -> Optional[str]:
    """Shared validator for the ``timezone`` field on every birth-shaped model."""
    if value is None:
        return None
    if not value.strip():
        raise ValueError(
            "timezone must be a zone name or 'auto'; omit it rather than sending an empty string"
        )
    if _OFFSET_LIKE.match(value):
        raise ValueError(
            f"timezone takes a zone name, not an offset; use timezone_offset for {value!r}"
        )
    return value


class BirthData(BaseModel):
    """Birth-moment input shared across natal, transits, Human Design, Vedic.

    Required: ``date`` (YYYY-MM-DD), ``time`` (HH:MM:SS), ``latitude`` and
    ``longitude`` in decimal degrees.

    The coordinates used to default to 0, which sent a real request for 0N 0E,
    six hundred kilometres off the coast of Ghana, and the server could not tell
    that apart from a deliberate one. api-calc stopped defaulting them in
    2.141.0: every ``/reports/*`` path answers 400 without them, and the JSON
    chart endpoints answer with a Deprecation header until 2026-11-09 and a 400
    after it. ``timezone_offset`` still defaults to 0, meaning UTC, and is
    counted in hours: 5.5 for India, not 330.
    """

    model_config = _API_CONFIG

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    timezone_offset: float = Field(default=0, alias="timezoneOffset", ge=-14, le=14)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    house_system: str = Field(default="P", alias="houseSystem")
    name: Optional[str] = None
    city: Optional[str] = None
    zodiac_type: Optional[str] = Field(default=None, alias="zodiacType")
    ayanamsa_id: Optional[float] = Field(default=None, alias="ayanamsaId")
    cosmogram: Optional[bool] = None
    timezone: Optional[str] = None

    _validate_timezone = field_validator("timezone")(_check_timezone)



class SynastryRequest(BaseModel):
    """Two-chart relationship analysis. Both charts use :class:`BirthData`."""

    model_config = _API_CONFIG

    chart1: BirthData
    chart2: BirthData
    orb_factor: Optional[float] = Field(default=None, alias="orbFactor")


class TransitsRequest(BaseModel):
    """Transits to a natal chart at a target moment.

    ``transit_date`` is required and names the moment to transit to; pass
    ``transit_time`` and ``transit_tz_offset`` when the hour matters.
    """

    model_config = _API_CONFIG

    # Birth fields are inlined rather than nested under `birth: BirthData` to
    # match the on-the-wire shape for /transits (flat object, not nested).
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    timezone_offset: float = Field(default=0, alias="timezoneOffset")
    latitude: float = 0
    longitude: float = 0
    transit_date: str = Field(alias="transitDate", pattern=r"^\d{4}-\d{2}-\d{2}$")
    transit_time: Optional[str] = Field(default=None, alias="transitTime")
    transit_tz_offset: Optional[float] = Field(default=None, alias="transitTzOffset")
    timezone: Optional[str] = None

    _validate_timezone = field_validator("timezone")(_check_timezone)



class VedicDashaRequest(BaseModel):
    """Birth-moment input for Vedic dasha endpoints (vimshottari/yogini/ashtottari/...).

    Same shape as :class:`BirthData`; declared separately for clarity at the
    call site. Sidereal calculations default to Lahiri ayanamsa server-side.
    """

    model_config = _API_CONFIG

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    timezone_offset: float = Field(default=0, alias="timezoneOffset")
    latitude: float = 0
    longitude: float = 0
    ayanamsa_id: Optional[float] = Field(default=None, alias="ayanamsaId")
    start_date: Optional[str] = Field(default=None, alias="startDate")
    end_date: Optional[str] = Field(default=None, alias="endDate")
    timezone: Optional[str] = None

    _validate_timezone = field_validator("timezone")(_check_timezone)



__all__ = [
    "BirthData",
    "SynastryRequest",
    "TransitsRequest",
    "VedicDashaRequest",
]
