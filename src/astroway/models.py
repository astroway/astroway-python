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
        timezone_offset=3, latitude=50.45, longitude=30.52,
    )
    chart = aw.chart.compute(birth)        # accepts BirthData or dict
    transits = aw.transits.compute(TransitsRequest(birth=birth, target_date="2027-01-01"))
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# All API field names are camelCase. Pydantic v2 picks them up via `alias` +
# `populate_by_name`, so users can write either `timezone_offset=3` (Python
# style) or `timezoneOffset=3` (matching the JSON wire format).
_API_CONFIG = ConfigDict(populate_by_name=True, extra="allow")


class BirthData(BaseModel):
    """Birth-moment input shared across natal, transits, Human Design, Vedic.

    Required: ``date`` (YYYY-MM-DD), ``time`` (HH:MM:SS).
    Latitude/longitude/timezone default to 0 — pass real values for accurate
    house cusps and ascendant.
    """

    model_config = _API_CONFIG

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    timezone_offset: float = Field(default=0, alias="timezoneOffset")
    latitude: float = 0
    longitude: float = 0
    house_system: str = Field(default="P", alias="houseSystem")
    name: Optional[str] = None
    city: Optional[str] = None
    zodiac_type: Optional[str] = Field(default=None, alias="zodiacType")
    ayanamsa_id: Optional[float] = Field(default=None, alias="ayanamsaId")
    cosmogram: Optional[bool] = None


class SynastryRequest(BaseModel):
    """Two-chart relationship analysis. Both charts use :class:`BirthData`."""

    model_config = _API_CONFIG

    chart1: BirthData
    chart2: BirthData
    orb_factor: Optional[float] = Field(default=None, alias="orbFactor")


class TransitsRequest(BaseModel):
    """Transits to a natal chart at a target moment.

    ``target_date`` defaults to "now" when omitted — pass an explicit
    ``YYYY-MM-DD`` (and optionally ``target_time``) for a fixed date.
    """

    model_config = _API_CONFIG

    # Birth fields are inlined rather than nested under `birth: BirthData` to
    # match the on-the-wire shape for /transits (flat object, not nested).
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    timezone_offset: float = Field(default=0, alias="timezoneOffset")
    latitude: float = 0
    longitude: float = 0
    target_date: Optional[str] = Field(default=None, alias="targetDate")
    target_time: Optional[str] = Field(default=None, alias="targetTime")
    target_timezone_offset: Optional[float] = Field(
        default=None, alias="targetTimezoneOffset"
    )
    target_latitude: Optional[float] = Field(default=None, alias="targetLatitude")
    target_longitude: Optional[float] = Field(default=None, alias="targetLongitude")


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


__all__ = [
    "BirthData",
    "SynastryRequest",
    "TransitsRequest",
    "VedicDashaRequest",
]
