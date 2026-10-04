"""Contract tests for the display-label to internal-key boundary.

Several service schemas accept friendly labels (``Blocked``, ``Blocking``) while
the normalized models expose internal keys (``blocked``, ``blocking``). The
normalizers bridge that gap. Nothing else enforces it, and a mismatch is silent:
a comparison that never matches simply does nothing rather than failing. These
tests make the contract explicit for every label the schemas advertise.
"""

from __future__ import annotations

import pytest

from custom_components.controld_manager.models import (
    default_rule_mode_labels,
    default_rule_mode_options,
    normalize_default_rule_mode,
    normalize_service_mode,
    rule_action_key_from_action_do,
    rule_action_options,
    service_mode_labels,
    service_mode_options,
)


@pytest.mark.parametrize("label", service_mode_labels())
def test_every_service_label_normalizes_to_a_model_key(label: str) -> None:
    """A label the schema accepts must resolve to a key the model produces."""
    assert normalize_service_mode(label) in service_mode_options()


@pytest.mark.parametrize("label", default_rule_mode_labels())
def test_every_default_rule_label_normalizes_to_a_model_key(label: str) -> None:
    """A default-rule label the schema accepts must resolve to a model key."""
    assert normalize_default_rule_mode(label) in default_rule_mode_options()


@pytest.mark.parametrize("key", service_mode_options())
def test_service_keys_normalize_to_themselves(key: str) -> None:
    """A key is already normalized, so it must pass through unchanged."""
    assert normalize_service_mode(key) == key


@pytest.mark.parametrize("key", default_rule_mode_options())
def test_default_rule_keys_normalize_to_themselves(key: str) -> None:
    """A default-rule key is already normalized and must pass through."""
    assert normalize_default_rule_mode(key) == key


def test_rule_action_options_are_already_keys() -> None:
    """The rule schema offers keys directly, so no normalization is needed."""
    produced = {rule_action_key_from_action_do(code) for code in (0, 1, 2, 3)}
    assert produced <= set(rule_action_options())


def test_labels_and_keys_are_distinct_sets() -> None:
    """The two vocabularies really are different, which is why this matters."""
    assert set(service_mode_labels()) != set(service_mode_options())
    assert set(default_rule_mode_labels()) != set(default_rule_mode_options())
