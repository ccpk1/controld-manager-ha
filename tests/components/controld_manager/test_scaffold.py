"""Basic scaffold tests for Control D Manager."""

from custom_components.controld_manager.const import DOMAIN


def test_domain_constant() -> None:
    """Verify the scaffold domain constant."""
    assert DOMAIN == "controld_manager"