"""Pydantic models — call-site usage + dict ↔ model interop."""

from __future__ import annotations

import json

import httpx
import pytest

from astroway import (
    Astroway,
    AsyncAstroway,
    BirthData,
    SynastryRequest,
    TransitsRequest,
    VedicDashaRequest,
)


class _Recorder(httpx.BaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            content=json.dumps({"ok": True, "data": {"echo": True}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


class _AsyncRecorder(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            content=json.dumps({"ok": True, "data": {"echo": True}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


# ─── Field validation + alias roundtrip ──────────────────────────


def test_birth_data_accepts_python_field_names() -> None:
    b = BirthData(date="1990-07-14", time="14:30:00", timezone_offset=3, latitude=50.45, longitude=30.52)
    assert b.timezone_offset == 3
    # On the wire, the alias `timezoneOffset` is used.
    payload = b.model_dump(by_alias=True, exclude_none=True)
    assert payload["timezoneOffset"] == 3
    assert "timezone_offset" not in payload


def test_birth_data_accepts_camel_case_aliases() -> None:
    b = BirthData(
        date="1990-07-14",
        time="14:30:00",
        timezoneOffset=3,
        houseSystem="W",
    )
    assert b.timezone_offset == 3
    assert b.house_system == "W"


def test_birth_data_validates_date_format() -> None:
    with pytest.raises(ValueError):
        BirthData(date="not-a-date", time="14:30:00")


def test_birth_data_validates_time_format() -> None:
    with pytest.raises(ValueError):
        BirthData(date="1990-07-14", time="14:30")


def test_birth_data_omits_unset_optional_fields_on_dump() -> None:
    b = BirthData(date="1990-07-14", time="14:30:00")
    payload = b.model_dump(by_alias=True, exclude_none=True)
    assert "name" not in payload
    assert "city" not in payload
    assert "ayanamsaId" not in payload


# ─── Sync client accepts Pydantic input ──────────────────────────


def test_sync_namespace_accepts_pydantic_birth_data() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    birth = BirthData(date="1990-07-14", time="14:30:00", timezone_offset=3, latitude=50.45, longitude=30.52)
    aw.chart.compute(birth)  # type: ignore[attr-defined]
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body == {
        "date": "1990-07-14",
        "time": "14:30:00",
        "timezoneOffset": 3,
        "latitude": 50.45,
        "longitude": 30.52,
        "houseSystem": "P",
    }


def test_sync_namespace_still_accepts_dict() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.chart.compute({"date": "1990-07-14", "time": "14:30:00"})  # type: ignore[attr-defined]
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body == {"date": "1990-07-14", "time": "14:30:00"}


def test_synastry_request_serializes_with_aliases() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    req = SynastryRequest(
        chart1=BirthData(date="1990-07-14", time="14:30:00", timezone_offset=3, latitude=50.45, longitude=30.52),
        chart2=BirthData(date="1992-03-22", time="09:15:00", timezone_offset=2, latitude=48.85, longitude=2.35),
        orb_factor=1.5,
    )
    aw.synastry.compute(req)  # type: ignore[attr-defined]
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body["orbFactor"] == 1.5
    assert body["chart1"]["timezoneOffset"] == 3


def test_transits_request_inlined_birth_fields() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.transits.compute(  # type: ignore[attr-defined]
        TransitsRequest(
            date="1990-07-14",
            time="14:30:00",
            timezone_offset=3,
            latitude=50.45,
            longitude=30.52,
            target_date="2027-01-01",
        )
    )
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body["targetDate"] == "2027-01-01"
    assert body["timezoneOffset"] == 3


def test_vedic_dasha_request_accepts_ayanamsa() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.vedic.dashas_vimshottari_maha(  # type: ignore[attr-defined]
        VedicDashaRequest(
            date="1985-07-22",
            time="06:45:00",
            timezone_offset=5.5,
            latitude=19.07,
            longitude=72.87,
            ayanamsa_id=1,
        )
    )
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body["ayanamsaId"] == 1


# ─── Async client parity ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_namespace_accepts_pydantic_input() -> None:
    transport = _AsyncRecorder()
    async with AsyncAstroway(api_key="aw_test_x", transport=transport) as aw:
        await aw.chart.compute(  # type: ignore[attr-defined]
            BirthData(date="1990-07-14", time="14:30:00", timezone_offset=3)
        )
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body["timezoneOffset"] == 3
