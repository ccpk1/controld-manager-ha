"""API client tests for Control D Manager."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

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
