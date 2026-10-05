"""Tests for the activity log and domain test (Phase 2b).

Both are read-only diagnostics. The important behaviours are the relative window
conversion, honest paging metadata, the verdict mapping, and that a block is
reported as data rather than an error.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from custom_components.controld_manager.managers.integration_manager import (
    ControlDIntegrationError,
    IntegrationManager,
)
from custom_components.controld_manager.models import (
    ControlDActivityLogPage,
    ControlDDnsVerdict,
    ControlDEndpointSummary,
    ControlDRegistry,
    ControlDUser,
)
from custom_components.controld_manager.utils.time_window import (
    ACTIVITY_LOG_WINDOWS,
    DEFAULT_ACTIVITY_LOG_WINDOW,
    window_to_timedelta,
)

_CONFIG_ENTRY_ID = "entry-1"


class _Runtime:
    """Minimal runtime stand-in carrying a registry and a mocked client."""

    def __init__(self, registry: ControlDRegistry, client: Any) -> None:
        """Store the registry and client the manager reads."""
        self.registry = registry
        self.client = client


def _manager(*, client: Any, with_user: bool = True) -> IntegrationManager:
    """Return an integration manager with an optional analytics region."""
    registry = ControlDRegistry(
        user=(
            ControlDUser(
                instance_id="user-1", account_pk="pk-1", stats_endpoint="america"
            )
            if with_user
            else None
        )
    )
    manager = IntegrationManager.__new__(IntegrationManager)
    manager.attach_runtime(_Runtime(registry, client))  # type: ignore[arg-type]
    return manager


@pytest.mark.parametrize("label", ACTIVITY_LOG_WINDOWS)
def test_every_supported_window_resolves(label: str) -> None:
    """Each advertised window maps to a positive duration."""
    assert window_to_timedelta(label) > timedelta(0)


def test_default_window_is_the_narrowest_useful_one() -> None:
    """The default stays short so a first call is cheap."""
    assert window_to_timedelta(DEFAULT_ACTIVITY_LOG_WINDOW) == timedelta(hours=1)


def test_unknown_window_raises() -> None:
    """An unsupported window fails loudly rather than querying something else."""
    with pytest.raises(ValueError):
        window_to_timedelta("99y")


async def test_activity_log_computes_a_relative_window() -> None:
    """The window label becomes an explicit start and end the client receives."""
    client = AsyncMock()
    client.async_get_activity_log = AsyncMock(
        return_value=ControlDActivityLogPage(records=(), page=0, page_size=50)
    )
    manager = _manager(client=client)

    response = await manager.async_build_activity_log_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        window="24h",
        page=0,
        page_size=50,
        sort_order="desc",
    )

    start = datetime.fromisoformat(str(response["window_start"]))
    end = datetime.fromisoformat(str(response["window_end"]))
    assert end - start == timedelta(hours=24)
    assert response["window"] == "24h"
    assert client.async_get_activity_log.await_args.args[0] == "america"


async def test_activity_log_reports_has_more_without_a_total() -> None:
    """A full page reports more pages exist and never claims a total."""
    client = AsyncMock()
    client.async_get_activity_log = AsyncMock(
        return_value=ControlDActivityLogPage(
            records=({"question": "a2z.com"},) * 50, page=0, page_size=50
        )
    )
    manager = _manager(client=client)

    response = await manager.async_build_activity_log_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        window="1h",
        page=0,
        page_size=50,
        sort_order="desc",
    )

    assert response["has_more"] is True
    assert response["page_size"] == 50
    assert len(response["records"]) == 50
    assert "total" not in response


async def test_activity_log_maps_the_action_label_to_the_client_code() -> None:
    """A friendly action label becomes the numeric code the API expects."""
    client = AsyncMock()
    client.async_get_activity_log = AsyncMock(
        return_value=ControlDActivityLogPage(records=(), page=0, page_size=50)
    )
    manager = _manager(client=client)

    await manager.async_build_activity_log_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        window="1h",
        page=0,
        page_size=50,
        sort_order="desc",
        query_action="blocked",
    )

    assert client.async_get_activity_log.await_args.kwargs["action"] == 0


async def test_activity_log_requires_a_known_analytics_region() -> None:
    """Without a resolved region the call fails cleanly, not with a KeyError."""
    client = AsyncMock()
    manager = _manager(client=client, with_user=False)

    with pytest.raises(ControlDIntegrationError):
        await manager.async_build_activity_log_response(
            config_entry_id=_CONFIG_ENTRY_ID,
            window="1h",
            page=0,
            page_size=50,
            sort_order="desc",
        )


@pytest.mark.parametrize(
    ("blocked", "rcode", "source", "expected_label"),
    [
        (True, 5, "bl", "filter"),
        (False, 0, "svc", "service"),
        (False, 0, "rules", "custom"),
        (False, 0, "default", "default"),
    ],
    ids=["blocked-by-filter", "service", "custom", "default"],
)
async def test_domain_test_maps_the_verdict_source(
    blocked: bool, rcode: int, source: str, expected_label: str
) -> None:
    """The vendor verdict vocabulary is translated to the trigger vocabulary."""
    client = AsyncMock()
    client.async_get_dns_verdict = AsyncMock(
        return_value=ControlDDnsVerdict(
            domain="a2z.com",
            record_type="A",
            rcode=rcode,
            is_blocked=blocked,
            profile_pk="p-1",
            source=source,
            action=0 if blocked else 1,
            match="x-hagezi-light",
        )
    )
    manager = _manager(client=client)

    response = await manager.async_build_domain_test_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        endpoint_id="vlan60",
        domain="a2z.com",
        record_type="A",
    )

    assert response["is_blocked"] is blocked
    assert response["rcode"] == rcode
    assert response["source"] == source
    assert response["source_label"] == expected_label
    assert response["domain"] == "a2z.com"


async def test_domain_test_without_a_verdict_is_not_an_error() -> None:
    """No matching policy is reported as data, with empty cause fields."""
    client = AsyncMock()
    client.async_get_dns_verdict = AsyncMock(
        return_value=ControlDDnsVerdict(
            domain="example.com",
            record_type="A",
            rcode=0,
            is_blocked=False,
        )
    )
    manager = _manager(client=client)

    response = await manager.async_build_domain_test_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        endpoint_id="vlan60",
        domain="example.com",
        record_type="A",
    )

    assert response["is_blocked"] is False
    assert response["source"] is None
    assert response["source_label"] is None
    assert response["match"] is None
    assert response["answers"] == []


def test_responses_are_json_serializable() -> None:
    """Both payloads survive json.dumps."""
    import json

    assert json.dumps({"has_more": True, "records": [{"a": 1}]})
    assert cast(Any, {"is_blocked": True})["is_blocked"] is True


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        pytest.param(-1, "failed", id="failed"),
        pytest.param(0, "blocked", id="blocked"),
        pytest.param(1, "bypassed", id="bypassed"),
        pytest.param(3, "redirected", id="redirected"),
    ],
)
async def test_every_action_code_is_named_on_the_record(
    action: int, expected: str
) -> None:
    """The raw codes are not contiguous and one is negative, so each is named.

    A caller reading `action` alone cannot tell blocked from bypassed, and the
    codes skip 2, so the label is what makes a record interpretable.
    """
    client = AsyncMock()
    client.async_get_activity_log = AsyncMock(
        return_value=ControlDActivityLogPage(
            records=({"action": action, "question": "example.com"},),
            page=0,
            page_size=50,
        )
    )
    manager = _manager(client=client)

    response = await manager.async_build_activity_log_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        window="1h",
        page=0,
        page_size=50,
        sort_order="desc",
    )

    record = cast(dict[str, Any], response["records"][0])
    assert record["action_label"] == expected
    # The raw code is left untouched so nothing is lost to the relabelling.
    assert record["action"] == action


async def test_an_empty_endpoint_name_is_resolved_from_the_inventory() -> None:
    """The vendor sends `endpointName` empty, so the name we hold is filled in.

    Without this the record identifies its device only by an opaque id, and an
    empty string reads as "this endpoint has no name" rather than "unpopulated".
    """
    client = AsyncMock()
    client.async_get_activity_log = AsyncMock(
        return_value=ControlDActivityLogPage(
            records=(
                {"action": 0, "endpointId": "ep-1", "endpointName": ""},
                {"action": 0, "endpointId": "ep-2", "endpointName": ""},
            ),
            page=0,
            page_size=50,
        )
    )
    manager = _manager(client=client)
    registry = manager.runtime.registry
    registry.endpoints["ep-1"] = ControlDEndpointSummary(
        device_id="ep-1",
        endpoint_pk="pk-1",
        name="kadens-phone",
        owning_profile_pk="profile-1",
    )

    response = await manager.async_build_activity_log_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        window="1h",
        page=0,
        page_size=50,
        sort_order="desc",
    )

    resolved, unknown = cast(list[dict[str, Any]], response["records"])
    assert resolved["endpointName"] == "kadens-phone"
    # An endpoint we no longer hold keeps the id the caller can still act on.
    assert unknown["endpointId"] == "ep-2"
    assert unknown["endpointName"] == ""
