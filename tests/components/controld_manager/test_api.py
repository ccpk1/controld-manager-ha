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
