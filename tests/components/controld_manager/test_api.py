"""API client tests for Control D Manager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.controld_manager.api import ControlDAPIClient


async def test_client_normalizes_documented_envelopes() -> None:
    """Validate the documented envelope shape for users, profiles, and devices."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))

    user_request = AsyncMock(return_value={"body": {"id": "user-123", "PK": "pk-1"}})
    with patch.object(client, "_async_get_json", user_request):
        assert await client.async_get_user() == {"id": "user-123", "PK": "pk-1"}

    profiles_request = AsyncMock(return_value={"body": {"profiles": [{"PK": "p-1"}]}})
    with patch.object(client, "_async_get_json", profiles_request):
        assert await client.async_get_profiles() == [{"PK": "p-1"}]

    devices_request = AsyncMock(
        return_value={"body": {"devices": [{"device_id": "device-1"}]}}
    )
    with patch.object(client, "_async_get_json", devices_request):
        assert await client.async_get_devices() == [{"device_id": "device-1"}]


async def test_client_flattens_nested_service_catalog() -> None:
    """Normalize nested category catalogs into flat service rows."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))

    service_catalog_request = AsyncMock(
        return_value={
            "body": {
                "categories": [
                    {
                        "PK": "audio",
                        "name": "Audio",
                        "services": [
                            {
                                "PK": "amazonmusic",
                                "name": "Amazon Music",
                                "unlock_location": "JFK",
                            }
                        ],
                    }
                ]
            }
        }
    )
    with patch.object(client, "_async_get_json", service_catalog_request):
        assert await client.async_get_service_catalog() == [
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "unlock_location": "JFK",
                "category": "audio",
            }
        ]


async def test_client_flattens_nested_service_catalog_under_services_key() -> None:
    """Normalize nested category groups even when they are stored under services."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))

    service_catalog_request = AsyncMock(
        return_value={
            "body": {
                "services": [
                    {
                        "category": "audio",
                        "name": "Audio",
                        "services": [
                            {
                                "PK": "amazonmusic",
                                "name": "Amazon Music",
                                "unlock_location": "JFK",
                            }
                        ],
                    }
                ]
            }
        }
    )
    with patch.object(client, "_async_get_json", service_catalog_request):
        assert await client.async_get_service_catalog() == [
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "unlock_location": "JFK",
                "category": "audio",
            }
        ]


async def test_client_preserves_mixed_flat_and_nested_service_rows() -> None:
    """Normalize service catalogs that mix flat rows with nested category groups."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))

    service_catalog_request = AsyncMock(
        return_value={
            "body": {
                "services": [
                    {
                        "PK": "amazonmusic",
                        "name": "Amazon Music",
                        "category": "audio",
                    },
                    {
                        "category": "shop",
                        "name": "Shop",
                        "services": [
                            {
                                "PK": 1688,
                                "name": 1688,
                                "unlock_location": "JFK",
                            }
                        ],
                    },
                ]
            }
        }
    )
    with patch.object(client, "_async_get_json", service_catalog_request):
        assert await client.async_get_service_catalog() == [
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "category": "audio",
            },
            {
                "PK": 1688,
                "name": 1688,
                "unlock_location": "JFK",
                "category": "shop",
            },
        ]


async def test_client_fetches_account_analytics() -> None:
    """Fetch account analytics from the stats-endpoint host."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    start_time = datetime(2026, 4, 7, 0, 0, 0, tzinfo=UTC)
    end_time = datetime(2026, 4, 8, 0, 0, 0, tzinfo=UTC)

    analytics_request = AsyncMock(
        side_effect=(
            {
                "body": {
                    "count": 9950,
                    "startTime": "2026-04-07T00:00:00Z",
                    "endTime": "2026-04-08T00:00:00Z",
                }
            },
            {
                "body": {
                    "count": 72318,
                    "startTime": "2026-04-07T00:00:00Z",
                    "endTime": "2026-04-08T00:00:00Z",
                }
            },
            {
                "body": {
                    "count": 0,
                    "startTime": "2026-04-07T00:00:00Z",
                    "endTime": "2026-04-08T00:00:00Z",
                }
            },
            {
                "body": {
                    "count": 0,
                    "startTime": "2026-04-07T00:00:00Z",
                    "endTime": "2026-04-08T00:00:00Z",
                }
            },
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        analytics = await client.async_get_account_analytics(
            "america",
            start_time=start_time,
            end_time=end_time,
        )

    assert analytics.total_queries == 82268
    assert analytics.blocked_queries == 9950
    assert analytics.bypassed_queries == 72318
    assert analytics.redirected_queries == 0
    assert analytics.blocked_queries_ratio == pytest.approx(12.094617591287014)
    assert analytics.start_time == datetime.fromisoformat("2026-04-07T00:00:00+00:00")
    assert analytics.end_time == datetime.fromisoformat("2026-04-08T00:00:00+00:00")

    assert len(analytics_request.await_args_list) == 4
    assert [call.kwargs["params"] for call in analytics_request.await_args_list] == [
        {
            "startTime": "2026-04-07T00:00:00.000Z",
            "endTime": "2026-04-08T00:00:00.000Z",
            "action[]": "0",
        },
        {
            "startTime": "2026-04-07T00:00:00.000Z",
            "endTime": "2026-04-08T00:00:00.000Z",
            "action[]": "1",
        },
        {
            "startTime": "2026-04-07T00:00:00.000Z",
            "endTime": "2026-04-08T00:00:00.000Z",
            "action[]": "2",
        },
        {
            "startTime": "2026-04-07T00:00:00.000Z",
            "endTime": "2026-04-08T00:00:00.000Z",
            "action[]": "3",
        },
    ]


async def test_client_preserves_requested_window_when_bucket_bounds_missing() -> None:
    """Preserve the requested reporting window when bucket totals omit timestamps."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    start_time = datetime(2026, 4, 7, 0, 0, 0, tzinfo=UTC)
    end_time = datetime(2026, 4, 8, 0, 0, 0, tzinfo=UTC)

    analytics_request = AsyncMock(
        side_effect=(
            {"body": {"count": 8100}},
            {"body": {"count": 49700}},
            {"body": {"count": 0}},
            {
                "body": {
                    "count": 26,
                    "startTime": "2026-04-08T04:00:00Z",
                    "endTime": "2026-04-08T12:00:00Z",
                }
            },
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        analytics = await client.async_get_account_analytics(
            "america",
            start_time=start_time,
            end_time=end_time,
        )

    assert analytics.total_queries == 57826
    assert analytics.blocked_queries == 8100
    assert analytics.bypassed_queries == 49700
    assert analytics.redirected_queries == 26
    assert analytics.blocked_queries_ratio == pytest.approx(14.007541243557913)
    assert analytics.start_time == datetime.fromisoformat("2026-04-08T04:00:00+00:00")
    assert analytics.end_time == datetime.fromisoformat("2026-04-08T12:00:00+00:00")


async def test_client_formats_local_day_window_as_utc() -> None:
    """Convert a local-day reporting window into the UTC analytics query format."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    eastern = timezone(timedelta(hours=-4))
    start_time = datetime(2026, 4, 7, 0, 0, 0, tzinfo=eastern)
    end_time = datetime(2026, 4, 7, 23, 6, 8, tzinfo=eastern)

    analytics_request = AsyncMock(
        side_effect=(
            {
                "body": {
                    "count": 8100,
                    "startTime": "2026-04-07T04:00:00.000Z",
                    "endTime": "2026-04-08T03:06:08.000Z",
                }
            },
            {
                "body": {
                    "count": 49700,
                    "startTime": "2026-04-07T04:00:00.000Z",
                    "endTime": "2026-04-08T03:06:08.000Z",
                }
            },
            {
                "body": {
                    "count": 0,
                    "startTime": "2026-04-07T04:00:00.000Z",
                    "endTime": "2026-04-08T03:06:08.000Z",
                }
            },
            {
                "body": {
                    "count": 26,
                    "startTime": "2026-04-07T04:00:00.000Z",
                    "endTime": "2026-04-08T03:06:08.000Z",
                }
            },
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        await client.async_get_account_analytics(
            "america",
            start_time=start_time,
            end_time=end_time,
        )

    assert [call.kwargs["params"] for call in analytics_request.await_args_list] == [
        {
            "startTime": "2026-04-07T04:00:00.000Z",
            "endTime": "2026-04-08T03:06:08.000Z",
            "action[]": "0",
        },
        {
            "startTime": "2026-04-07T04:00:00.000Z",
            "endTime": "2026-04-08T03:06:08.000Z",
            "action[]": "1",
        },
        {
            "startTime": "2026-04-07T04:00:00.000Z",
            "endTime": "2026-04-08T03:06:08.000Z",
            "action[]": "2",
        },
        {
            "startTime": "2026-04-07T04:00:00.000Z",
            "endTime": "2026-04-08T03:06:08.000Z",
            "action[]": "3",
        },
    ]


async def test_client_counts_redirected_queries_from_action_three() -> None:
    """Treat analytics action 3 as the redirected bucket."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    start_time = datetime(2026, 4, 8, 4, 0, 0, tzinfo=UTC)
    end_time = datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC)

    analytics_request = AsyncMock(
        side_effect=(
            {"body": {"count": 8608}},
            {"body": {"count": 53395}},
            {"body": {"count": 0}},
            {
                "body": {
                    "count": 28,
                    "startTime": "2026-04-08T04:00:00Z",
                    "endTime": "2026-04-08T12:00:00Z",
                }
            },
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        analytics = await client.async_get_account_analytics(
            "america",
            start_time=start_time,
            end_time=end_time,
        )

    assert analytics.blocked_queries == 8608
    assert analytics.bypassed_queries == 53395
    assert analytics.redirected_queries == 28
    assert analytics.total_queries == 62031


async def test_client_combines_redirect_actions_two_and_three() -> None:
    """Combine both redirect-family analytics buckets into redirected queries."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    start_time = datetime(2026, 4, 8, 4, 0, 0, tzinfo=UTC)
    end_time = datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC)

    analytics_request = AsyncMock(
        side_effect=(
            {"body": {"count": 8608}},
            {"body": {"count": 53395}},
            {"body": {"count": 7}},
            {"body": {"count": 28}},
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        analytics = await client.async_get_account_analytics(
            "america",
            start_time=start_time,
            end_time=end_time,
        )

    assert analytics.redirected_queries == 35
    assert analytics.total_queries == 62038


async def test_client_fetches_profile_analytics_with_profile_scope() -> None:
    """Pass the profile selector through every analytics action-bucket query."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    start_time = datetime(2026, 4, 8, 4, 0, 0, tzinfo=UTC)
    end_time = datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC)

    analytics_request = AsyncMock(
        side_effect=(
            {"body": {"count": 10}},
            {"body": {"count": 20}},
            {"body": {"count": 3}},
            {"body": {"count": 4}},
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        analytics = await client.async_get_profile_analytics(
            "america",
            "886818chik7jg",
            start_time=start_time,
            end_time=end_time,
        )

    assert analytics.total_queries == 37
    profile_ids = [
        call.kwargs["params"]["profileId"] for call in analytics_request.await_args_list
    ]
    assert profile_ids == [
        "886818chik7jg",
        "886818chik7jg",
        "886818chik7jg",
        "886818chik7jg",
    ]


async def test_client_fetches_endpoint_analytics_with_profile_and_endpoint_scope() -> (
    None
):
    """Pass both profile and endpoint selectors through every bucket query."""
    client = ControlDAPIClient("token", cast(ClientSession, MagicMock()))
    start_time = datetime(2026, 4, 8, 4, 0, 0, tzinfo=UTC)
    end_time = datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC)

    analytics_request = AsyncMock(
        side_effect=(
            {"body": {"count": 1}},
            {"body": {"count": 2}},
            {"body": {"count": 3}},
            {"body": {"count": 4}},
        )
    )

    with patch.object(client, "_async_get_external_json", analytics_request):
        analytics = await client.async_get_endpoint_analytics(
            "america",
            "628266chij53t",
            "asnozvs6a7",
            start_time=start_time,
            end_time=end_time,
        )

    assert analytics.total_queries == 10
    profile_ids = [
        call.kwargs["params"]["profileId"] for call in analytics_request.await_args_list
    ]
    endpoint_ids = [
        call.kwargs["params"]["endpointId[]"]
        for call in analytics_request.await_args_list
    ]
    assert profile_ids == [
        "628266chij53t",
        "628266chij53t",
        "628266chij53t",
        "628266chij53t",
    ]
    assert endpoint_ids == [
        ["asnozvs6a7"],
        ["asnozvs6a7"],
        ["asnozvs6a7"],
        ["asnozvs6a7"],
    ]
