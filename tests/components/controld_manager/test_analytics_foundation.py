"""Phase 0 foundation tests: analytics reads, exceptions, resolver, truncation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.controld_manager.api import ControlDAPIClient
from custom_components.controld_manager.api.exceptions import (
    ControlDApiConnectionError,
    ControlDApiMaintenanceError,
    ControlDApiRateLimitError,
    ControlDApiResponseError,
)
from custom_components.controld_manager.utils.analytics_labels import (
    build_analytics_label_map,
    resolve_ranked_rows,
)
from custom_components.controld_manager.utils.truncation import (
    build_limit_meta,
    build_page_meta,
)

_WINDOW_START = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
_WINDOW_END = _WINDOW_START + timedelta(hours=1)


def _client() -> ControlDAPIClient:
    """Return a client with an unused mock session."""
    return ControlDAPIClient("token", cast(ClientSession, MagicMock()))


def _session_with_status(status: int, payload: Any = None) -> MagicMock:
    """Return a mock session whose request yields one canned response."""
    response = MagicMock()
    response.status = status
    response.content_length = 0 if payload is None else 1
    response.json = AsyncMock(return_value=payload)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = MagicMock(return_value=context)
    return session


async def test_activity_log_parses_records_and_meta() -> None:
    """The activity log returns normalized records with paging metadata."""
    client = _client()
    request = AsyncMock(
        return_value={
            "body": {
                "meta": {"page": 2, "pageSize": 50},
                "queries": [
                    {
                        "question": "a2z.com",
                        "action": 0,
                        "trigger": "filter",
                        "triggerValue": "x-hagezi-light",
                    }
                ],
            }
        }
    )
    with patch.object(client, "_async_get_external_json", request):
        page = await client.async_get_activity_log(
            "america",
            start_time=_WINDOW_START,
            end_time=_WINDOW_END,
            page=2,
            page_size=50,
        )

    assert page.page == 2
    assert page.page_size == 50
    assert page.records[0]["triggerValue"] == "x-hagezi-light"


async def test_activity_log_maps_vendor_filters_to_params() -> None:
    """Vendor-aligned filters are translated to the documented query names."""
    client = _client()
    request = AsyncMock(return_value={"body": {"meta": {}, "queries": []}})
    with patch.object(client, "_async_get_external_json", request):
        await client.async_get_activity_log(
            "america",
            start_time=_WINDOW_START,
            end_time=_WINDOW_END,
            search_question="a2z",
            action=0,
            trigger="custom",
            trigger_value="ccpk.us",
            endpoint_ids=["ep-1"],
            profile_id="p-1",
            protocols=["doh"],
            source_countries=["US"],
            status_code=0,
        )

    params = request.await_args.kwargs["params"]
    assert params["searchQuestion"] == "a2z"
    assert params["action"] == "0"
    assert params["trigger"] == "custom"
    assert params["triggerValue"] == "ccpk.us"
    assert params["endpointId[]"] == ["ep-1"]
    assert params["srcCountry[]"] == ["US"]
    # rcode is silently ignored upstream; statusCode is the working filter.
    assert params["statusCode"] == "0"
    assert "rcode" not in params


async def test_activity_log_rejects_missing_queries() -> None:
    """A malformed activity log payload raises a response error."""
    client = _client()
    request = AsyncMock(return_value={"body": {"meta": {}}})
    with (
        patch.object(client, "_async_get_external_json", request),
        pytest.raises(ControlDApiResponseError),
    ):
        await client.async_get_activity_log(
            "america", start_time=_WINDOW_START, end_time=_WINDOW_END
        )


async def test_ranked_reads_return_normalized_rows() -> None:
    """Ranked domains, triggers, and countries share one normalized shape."""
    client = _client()
    payload = {"body": {"counts": [{"value": "ads", "count": 5}]}}

    for method, kwargs in (
        (client.async_get_ranked_domains, {}),
        (client.async_get_trigger_breakdown, {"trigger": "filter"}),
        (client.async_get_source_countries, {}),
    ):
        request = AsyncMock(return_value=payload)
        with patch.object(client, "_async_get_external_json", request):
            rows = await method(
                "america",
                start_time=_WINDOW_START,
                end_time=_WINDOW_END,
                **kwargs,
            )
        assert rows == [{"value": "ads", "count": 5}]


@pytest.mark.parametrize(
    ("rcode", "expected_blocked"),
    [(0, False), (5, True)],
    ids=["allowed", "blocked"],
)
async def test_dns_verdict_reports_block_state(
    rcode: int, expected_blocked: bool
) -> None:
    """A REFUSED response is a block verdict, not a failure."""
    client = _client()
    payload = {
        "RCODE": rcode,
        "answerRRs": [{"rdataA": "142.250.177.78"}] if rcode == 0 else [],
        "controld": {
            "verdict": {
                "profileID": "p-1",
                "verdictSource": "bl",
                "verdictAction": "0" if expected_blocked else "1",
                "verdictMatch": "x-hagezi-light",
            }
        },
    }
    request = AsyncMock(return_value=payload)
    with patch.object(client, "_async_request_url", request):
        verdict = await client.async_get_dns_verdict("ep-1", "a2z.com")

    assert verdict.is_blocked is expected_blocked
    assert verdict.rcode == rcode
    assert verdict.source == "bl"
    assert request.await_args.kwargs["headers"] == {"Accept": "application/dns+json"}


async def test_dns_verdict_without_verdict_is_not_an_error() -> None:
    """No matching policy is reported as data, not raised."""
    client = _client()
    request = AsyncMock(return_value={"RCODE": 0, "answerRRs": []})
    with patch.object(client, "_async_request_url", request):
        verdict = await client.async_get_dns_verdict("ep-1", "example.com")

    assert verdict.is_blocked is False
    assert verdict.source is None
    assert verdict.profile_pk is None


async def test_write_methods_return_normalized_body() -> None:
    """A write returns the parsed body instead of discarding it."""
    client = _client()
    request = AsyncMock(return_value={"body": {"PK": "ep-1", "stats": 2}})
    with patch.object(client, "_async_request", request):
        body = await client.async_set_endpoint_analytics_logging("ep-1", stats=2)

    assert body == {"PK": "ep-1", "stats": 2}


async def test_write_returns_none_when_no_body() -> None:
    """A write with no response body returns None rather than raising."""
    client = _client()
    request = AsyncMock(return_value=None)
    with patch.object(client, "_async_request", request):
        body = await client.async_delete_profile_rules("p-1", ["a2z.com"])

    assert body is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, ControlDApiRateLimitError),
        (503, ControlDApiMaintenanceError),
        (500, ControlDApiResponseError),
    ],
)
async def test_transport_statuses_map_to_typed_errors(
    status: int, expected: type[Exception]
) -> None:
    """Rate limit, maintenance, and generic failures are distinguishable."""
    client = ControlDAPIClient(
        "token", cast(ClientSession, _session_with_status(status))
    )
    with pytest.raises(expected):
        await client.async_get_user()


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (ControlDApiConnectionError("x"), True),
        (ControlDApiMaintenanceError("x"), True),
        (ControlDApiRateLimitError("x"), True),
        (ControlDApiResponseError("x"), False),
    ],
)
def test_retryable_signal(error: Exception, retryable: bool) -> None:
    """Each exception class reports whether a retry may help."""
    assert cast(Any, error).retryable is retryable


def test_label_map_prefers_catalogs_and_keeps_variants() -> None:
    """Catalog labels resolve slugs; documented variants come from the alias map."""
    label_map = build_analytics_label_map(
        filters=[{"PK": "ads", "name": "Ads & Trackers"}],
        options=[{"PK": "ai_malware", "title": "AI Malware Filter"}],
    )

    assert label_map["ads"] == "Ads & Trackers"
    assert label_map["ai_malware"] == "AI Malware Filter"
    assert label_map["ads_small"] == "Ads & Trackers - Relaxed"


def test_resolve_ranked_rows_keeps_raw_value_and_flags_unmapped() -> None:
    """Every row keeps its raw value; unresolved slugs are flagged, not invented."""
    rows = [
        {"value": "ads", "count": 10},
        {"value": "mystery_slug", "count": 1},
    ]
    resolved = resolve_ranked_rows(rows, {"ads": "Ads & Trackers"})

    assert resolved[0] == {
        "value": "ads",
        "label": "Ads & Trackers",
        "label_resolved": True,
        "count": 10,
    }
    assert resolved[1]["value"] == "mystery_slug"
    assert resolved[1]["label"] == "mystery_slug"
    assert resolved[1]["label_resolved"] is False


@pytest.mark.parametrize(
    ("returned", "truncated"),
    [(24, False), (25, True)],
    ids=["below-limit", "at-limit"],
)
def test_limit_meta_flags_truncation(returned: int, truncated: bool) -> None:
    """A result that fills the limit is reported as truncated."""
    assert build_limit_meta(25, returned) == {
        "applied_limit": 25,
        "truncated": truncated,
    }


@pytest.mark.parametrize(
    ("returned", "has_more"),
    [(3, False), (5, True)],
    ids=["partial-page", "full-page"],
)
def test_page_meta_reports_more_records(returned: int, has_more: bool) -> None:
    """A full page means more records may exist; it does not confirm a total."""
    assert build_page_meta(0, 5, returned) == {
        "page": 0,
        "page_size": 5,
        "has_more": has_more,
    }
