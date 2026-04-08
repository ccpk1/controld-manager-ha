"""Async API client for Control D inventory reads."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession

from ..models import (
    ControlDInventoryPayload,
    ControlDProfileDetailPayload,
    ControlDUser,
)
from .exceptions import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)

DEFAULT_BASE_URL = "https://api.controld.com"


class ControlDAPIClient:
    """Async client for the documented Control D inventory endpoints."""

    def __init__(
        self, api_token: str, session: ClientSession, base_url: str = DEFAULT_BASE_URL
    ) -> None:
        """Initialize the API client."""
        self._api_token = api_token
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def async_get_instance_identity(self) -> ControlDUser:
        """Return the normalized instance identity used for config-entry anchoring."""
        user_payload = await self.async_get_user()
        instance_id = self._require_string(user_payload, "id")
        account_pk = self._require_string(user_payload, "PK")
        safe_countries = tuple(
            country
            for country in user_payload.get("safe_countries", [])
            if isinstance(country, str)
        )
        return ControlDUser(
            instance_id=instance_id,
            account_pk=account_pk,
            display_name=(
                self._optional_string(user_payload.get("name"))
                or self._optional_string(user_payload.get("email"))
                or self._optional_string(user_payload.get("username"))
            ),
            last_active=self._optional_string(user_payload.get("last_active")),
            stats_endpoint=self._optional_string(user_payload.get("stats_endpoint")),
            status=self._optional_string(user_payload.get("status")),
            safe_countries=safe_countries,
        )

    async def async_get_inventory(self) -> ControlDInventoryPayload:
        """Return the raw inventory payloads needed by the runtime foundation."""
        user, profiles, devices = await asyncio.gather(
            self.async_get_user(),
            self.async_get_profiles(),
            self.async_get_devices(),
        )
        return ControlDInventoryPayload(
            user=user,
            profiles=tuple(profiles),
            devices=tuple(devices),
        )

    async def async_get_profile_filters(self, profile_pk: str) -> list[dict[str, Any]]:
        """Fetch filter rows for one profile."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/filters")
        return self._extract_body_list(payload, "filters")

    async def async_get_profile_external_filters(
        self, profile_pk: str
    ) -> list[dict[str, Any]]:
        """Fetch third-party filter rows for one profile."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/filters/external")
        return self._extract_body_list(payload, "filters")

    async def async_get_profile_services(self, profile_pk: str) -> list[dict[str, Any]]:
        """Fetch service rows for one profile."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/services")
        return self._extract_body_list(payload, "services")

    async def async_get_profile_options(self, profile_pk: str) -> list[dict[str, Any]]:
        """Fetch the current sparse option-state rows for one profile."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/options")
        return self._extract_body_list(payload, "options")

    async def async_get_profile_default_rule(self, profile_pk: str) -> dict[str, Any]:
        """Fetch the current default-rule row for one profile."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/default")
        body = self._extract_body_mapping(payload)
        default_rule = body.get("default")
        if not isinstance(default_rule, dict):
            raise ControlDApiResponseError(
                "Control D response body is missing the expected 'default' mapping"
            )
        return default_rule

    async def async_get_profile_groups(self, profile_pk: str) -> list[dict[str, Any]]:
        """Fetch grouped-rule folders for one profile."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/groups")
        return self._extract_body_list(payload, "groups")

    async def async_get_profile_rules(self, profile_pk: str) -> list[dict[str, Any]]:
        """Fetch all rules for one profile, including grouped-rule members."""
        payload = await self._async_get_json(f"/profiles/{profile_pk}/rules/all")
        return self._extract_body_list(payload, "rules")

    async def async_get_profile_detail(
        self,
        profile_pk: str,
        *,
        include_services: bool,
        include_rules: bool,
    ) -> ControlDProfileDetailPayload:
        """Fetch the detail payloads required for one profile policy."""
        filters, external_filters, options, default_rule = await asyncio.gather(
            self.async_get_profile_filters(profile_pk),
            self.async_get_profile_external_filters(profile_pk),
            self.async_get_profile_options(profile_pk),
            self.async_get_profile_default_rule(profile_pk),
        )

        services: list[dict[str, Any]] = []
        if include_services:
            services = await self.async_get_profile_services(profile_pk)

        groups: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        if include_rules:
            groups, rules = await asyncio.gather(
                self.async_get_profile_groups(profile_pk),
                self.async_get_profile_rules(profile_pk),
            )

        return ControlDProfileDetailPayload(
            filters=tuple(filters),
            external_filters=tuple(external_filters),
            options=tuple(options),
            default_rule=default_rule,
            services=tuple(services),
            groups=tuple(groups),
            rules=tuple(rules),
        )

    async def async_get_profile_option_catalog(self) -> list[dict[str, Any]]:
        """Fetch the global profile-option catalog."""
        payload = await self._async_get_json("/profiles/options")
        return self._extract_body_list(payload, "options")

    async def async_get_service_categories(self) -> list[dict[str, Any]]:
        """Fetch service-category metadata."""
        payload = await self._async_get_json("/services/categories")
        return self._extract_body_list(payload, "categories")

    async def async_get_service_catalog(self) -> list[dict[str, Any]]:
        """Fetch the full service catalog."""
        payload = await self._async_get_json("/services/categories/all")
        body = self._extract_body_mapping(payload)

        services_or_categories = body.get("services")
        if isinstance(services_or_categories, list):
            return self._normalize_service_catalog_rows(services_or_categories)

        categories = body.get("categories")
        if isinstance(categories, list):
            return self._normalize_service_catalog_rows(categories)

        raise ControlDApiResponseError(
            "Control D response body is missing the expected 'services' or "
            "'categories' list"
        )

    def _normalize_service_catalog_rows(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize mixed flat and category-grouped service catalogs."""
        services: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ControlDApiResponseError(
                    "Control D response service catalog must contain only mappings"
                )

            nested_services = row.get("services")
            if isinstance(nested_services, list):
                category_pk = self._optional_string(row.get("PK"))
                if category_pk is None:
                    category_pk = self._optional_string(row.get("category"))
                if category_pk is None:
                    raise ControlDApiResponseError(
                        "Control D category payload is missing the expected "
                        "category identifier"
                    )

                for service in nested_services:
                    if not isinstance(service, dict):
                        raise ControlDApiResponseError(
                            "Control D category service rows must contain only mappings"
                        )

                    normalized_service = dict(service)
                    normalized_service.setdefault("category", category_pk)
                    services.append(normalized_service)
                continue

            services.append(dict(row))

        return services

    async def async_get_user(self) -> dict[str, Any]:
        """Fetch the authenticated Control D user payload."""
        payload = await self._async_get_json("/users")
        return self._extract_body_mapping(payload)

    async def async_get_profiles(self) -> list[dict[str, Any]]:
        """Fetch the profile inventory payload."""
        payload = await self._async_get_json("/profiles")
        return self._extract_body_list(payload, "profiles")

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Fetch the endpoint inventory payload."""
        payload = await self._async_get_json("/devices?last_activity=1")
        return self._extract_body_list(payload, "devices")

    async def async_set_profile_disable_until(
        self, profile_pk: str, disable_ttl: int
    ) -> None:
        """Disable or enable a profile using the documented disable-until contract."""
        await self._async_request(
            "PUT", f"/profiles/{profile_pk}", {"disable_ttl": disable_ttl}
        )

    async def async_set_profile_filter(
        self,
        profile_pk: str,
        filter_pk: str,
        *,
        enabled: bool,
        action_do: int,
        level_slug: str | None,
    ) -> None:
        """Update one profile filter using the browser-verified filter contract."""
        payload: dict[str, Any] = {"status": int(enabled), "do": action_do}
        if level_slug is not None:
            payload["lvl"] = level_slug
        await self._async_request(
            "PUT", f"/profiles/{profile_pk}/filters/filter/{filter_pk}", payload
        )

    async def async_set_profile_service(
        self,
        profile_pk: str,
        service_pk: str,
        *,
        enabled: bool,
        action_do: int,
    ) -> None:
        """Update one profile service row using the current action model."""
        await self._async_request(
            "PUT",
            f"/profiles/{profile_pk}/services/{service_pk}",
            {"do": action_do, "status": int(enabled)},
        )

    async def async_set_profile_rule(
        self,
        profile_pk: str,
        rule_pk: str,
        *,
        enabled: bool,
        action_do: int,
        group_pk: str | None,
        ttl: int | None,
        comment: str | None = None,
    ) -> None:
        """Update one profile rule using the current action model."""
        payload: dict[str, Any] = {"do": action_do, "status": int(enabled)}
        if group_pk is not None:
            payload["group"] = group_pk
        if ttl is not None:
            payload["ttl"] = ttl
        if comment is not None:
            payload["comment"] = comment
        await self._async_request(
            "PUT", f"/profiles/{profile_pk}/rules/{rule_pk}", payload
        )

    async def async_update_profile_rule_rich(
        self,
        profile_pk: str,
        rule_pk: str,
        *,
        enabled: bool,
        action_do: int,
        group_pk: str | None,
        comment: str,
        ttl: int | None,
    ) -> None:
        """Update one profile rule using the rich hostname-based contract."""
        payload: dict[str, Any] = {
            "do": action_do,
            "status": int(enabled),
            "via": "-1",
            "via_v6": "-1",
            "hostnames": [rule_pk],
            "group": 0 if group_pk is None else int(group_pk),
            "comment": comment,
        }
        if ttl is not None:
            payload["ttl"] = ttl
        await self._async_request("PUT", f"/profiles/{profile_pk}/rules", payload)

    async def async_create_profile_rules(
        self,
        profile_pk: str,
        hostnames: list[str],
        *,
        enabled: bool,
        action_do: int,
        group_pk: str | None,
        comment: str,
        ttl: int | None,
    ) -> None:
        """Create one or more profile rules using the browser-backed contract."""
        payload: dict[str, Any] = {
            "do": action_do,
            "status": int(enabled),
            "via": "-1",
            "via_v6": "-1",
            "hostnames": hostnames,
            "group": 0 if group_pk is None else int(group_pk),
            "comment": comment,
        }
        if ttl is not None:
            payload["ttl"] = ttl
        await self._async_request("POST", f"/profiles/{profile_pk}/rules", payload)

    async def async_delete_profile_rules(
        self,
        profile_pk: str,
        hostnames: list[str],
    ) -> None:
        """Delete one or more profile rules using the hostname-list contract."""
        await self._async_request(
            "DELETE",
            f"/profiles/{profile_pk}/rules",
            {"hostnames": hostnames},
        )

    async def async_set_profile_group(
        self,
        profile_pk: str,
        group_pk: str,
        *,
        name: str,
        enabled: bool,
        action_do: int | None,
    ) -> None:
        """Update one profile rule folder using the browser-backed group contract."""
        payload: dict[str, Any] = {
            "name": name,
            "status": int(enabled),
            "via": "-1",
            "via_v6": "-1",
        }
        if action_do is not None:
            payload["do"] = action_do
        await self._async_request(
            "PUT", f"/profiles/{profile_pk}/groups/{group_pk}", payload
        )

    async def async_set_profile_option(
        self,
        profile_pk: str,
        option_pk: str,
        *,
        enabled: bool,
        value: str | None = None,
    ) -> None:
        """Update one profile option using the browser-verified option contract."""
        payload: dict[str, Any] = {"status": int(enabled)}
        if value is not None:
            payload["value"] = value
        await self._async_request(
            "PUT", f"/profiles/{profile_pk}/options/{option_pk}", payload
        )

    async def async_set_profile_default_rule(
        self,
        profile_pk: str,
        *,
        action_do: int,
        via: str | None = None,
    ) -> None:
        """Update one profile default rule using the browser-verified contract."""
        payload: dict[str, Any] = {"do": action_do, "status": 1}
        if via is not None:
            payload["via"] = via
        await self._async_request("PUT", f"/profiles/{profile_pk}/default", payload)

    async def _async_get_json(self, path: str) -> Any:
        """Perform a GET request and decode JSON safely."""
        return await self._async_request("GET", path)

    async def _async_request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        """Perform an HTTP request and decode JSON when present."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers, json=payload
            ) as response:
                if response.status in (401, 403):
                    raise ControlDApiAuthError("Control D authentication failed")
                if response.status >= 400:
                    raise ControlDApiResponseError(
                        f"Control D returned unexpected status {response.status}"
                    )
                if response.content_length == 0:
                    return None
                return await response.json(content_type=None)
        except TimeoutError as err:
            raise ControlDApiConnectionError("Control D request timed out") from err
        except ClientError as err:
            raise ControlDApiConnectionError("Control D request failed") from err

    @property
    def _headers(self) -> dict[str, str]:
        """Return the documented authorization headers."""
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
        }

    @staticmethod
    def _extract_body_mapping(payload: Any) -> dict[str, Any]:
        """Extract a mapping body from a standard API response."""
        if not isinstance(payload, dict):
            raise ControlDApiResponseError(
                "Control D response payload must be a mapping"
            )
        body = payload.get("body")
        if not isinstance(body, dict):
            raise ControlDApiResponseError("Control D response body must be a mapping")
        return body

    @classmethod
    def _extract_body_list(cls, payload: Any, key: str) -> list[dict[str, Any]]:
        """Extract a list of mapping items from a nested response body."""
        body = cls._extract_body_mapping(payload)
        items = body.get(key)
        if not isinstance(items, list):
            raise ControlDApiResponseError(
                f"Control D response body is missing the expected {key!r} list"
            )
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                raise ControlDApiResponseError(
                    f"Control D response list {key!r} must contain only mappings"
                )
            normalized_items.append(item)
        return normalized_items

    @staticmethod
    def _require_string(payload: dict[str, Any], key: str) -> str:
        """Return a required string field from a payload."""
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ControlDApiResponseError(
                f"Control D payload is missing required string field {key!r}"
            )
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Return an optional string field from a payload."""
        return value if isinstance(value, str) and value else None
