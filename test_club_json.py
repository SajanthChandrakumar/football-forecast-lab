from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from enum import Enum
import gzip
from uuid import UUID
import json

import pytest
from fastapi.encoders import jsonable_encoder
from starlette.middleware.gzip import GZipMiddleware

import src.services.club_json as club_json


def test_native_large_payload_skips_fastapi_encoder_and_matches_encoded_json(monkeypatch):
    payload = {
        "fixtures": [
            {"id": index, "team": f"Club {index:02d}", "completed": index % 2 == 0, "probability": 0.123456789}
            for index in range(36)
        ],
        "metadata": {"version": "prediction-club-v2", "status": "fresh", "empty": None},
        "snapshot": "x" * (8 * 1024 * 1024),
    }
    encoder_calls = []
    monkeypatch.setattr(
        club_json, "jsonable_encoder",
        lambda value: (encoder_calls.append(value), jsonable_encoder(value))[1],
    )

    response = club_json.ClubJSONResponse(payload)

    assert encoder_calls == []
    assert json.loads(response.body) == jsonable_encoder(payload)


def test_datetime_date_and_enum_use_fastapi_encoder_fallback(monkeypatch):
    class State(Enum):
        READY = "ready"

    payload = {
        "captured_at": datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc),
        "match_day": date(2026, 10, 25),
        "state": State.READY,
        "id": UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
    }
    encoder_calls = []
    real_encoder = jsonable_encoder
    monkeypatch.setattr(
        club_json, "jsonable_encoder",
        lambda value: (encoder_calls.append(value), real_encoder(value))[1],
    )

    response = club_json.ClubJSONResponse(payload)

    assert len(encoder_calls) == 4
    assert json.loads(response.body) == real_encoder(payload)


def test_nan_is_rejected_without_encoder_fallback(monkeypatch):
    encoder_calls = []
    monkeypatch.setattr(club_json, "jsonable_encoder", lambda value: encoder_calls.append(value) or value)

    with pytest.raises(ValueError):
        club_json.ClubJSONResponse({"probability": float("nan")})

    assert encoder_calls == []


def test_response_emits_expected_asgi_status_headers_and_body():
    response = club_json.ClubJSONResponse(
        {"status": "processing", "n_runs": 5000},
        status_code=202,
        headers={"Retry-After": "3"},
    )
    sent = []

    async def run_response():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await response(
            {"type": "http", "asgi": {"version": "3.0"}, "method": "GET", "path": "/api/matches"},
            receive,
            send,
        )

    asyncio.run(run_response())

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = next(message for message in sent if message["type"] == "http.response.body")
    headers = {key.lower(): value for key, value in start["headers"]}
    assert start["status"] == 202
    assert headers[b"content-type"] == b"application/json"
    assert headers[b"retry-after"] == b"3"
    assert headers[b"content-length"] == str(len(body["body"])).encode("ascii")
    assert json.loads(body["body"]) == {"status": "processing", "n_runs": 5000}


def test_opt_in_gzip_has_consistent_headers_and_decompresses_to_the_json():
    payload = {"fixtures": [{"id": i, "name": "FC Zürich"} for i in range(500)]}
    response = club_json.ClubJSONResponse(
        payload,
        gzip_enabled=True,
        headers={"Vary": "Origin"},
    )

    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["content-length"] == str(len(response.body))
    assert response.headers["vary"] == "Origin, Accept-Encoding"
    assert json.loads(gzip.decompress(response.body)) == payload


@pytest.mark.parametrize("accept_encoding", ["gzip", "gzip;q=0"])
def test_gzip_negotiation_survives_outer_starlette_middleware(accept_encoding):
    payload = {"fixtures": [{"id": i, "name": "FC Zürich"} for i in range(500)]}
    response = club_json.ClubJSONResponse(payload, gzip_enabled=club_json.accepts_gzip(accept_encoding))
    sent = []

    async def app(scope, receive, send):
        await response(scope, receive, send)

    async def run_middleware():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await GZipMiddleware(app, minimum_size=1, compresslevel=9)(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/api/matches",
                "raw_path": b"/api/matches",
                "query_string": b"",
                "headers": [(b"accept-encoding", accept_encoding.encode())],
                "server": ("test", 80),
                "client": ("test", 1),
            },
            receive,
            send,
        )

    asyncio.run(run_middleware())

    body = next(message["body"] for message in sent if message["type"] == "http.response.body")
    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {key.lower(): value for key, value in start["headers"]}
    assert headers[b"content-length"] == str(len(body)).encode("ascii")
    if accept_encoding == "gzip":
        assert headers[b"content-encoding"] == b"gzip"
        assert json.loads(gzip.decompress(body)) == payload
    else:
        assert headers[b"content-encoding"] == b"identity"
        assert json.loads(body) == payload


@pytest.mark.parametrize("header, expected", [
    ("", False), ("gzip", True), ("br, GZIP;q=0.5", True),
    ("gzip;q=0", False), ("xgzip", False), ("gzip;q=invalid", False),
    ("*;q=0.7", True), ("gzip;q=0, *;q=1", False),
])
def test_gzip_quality_negotiation(header, expected):
    assert club_json.accepts_gzip(header) is expected
