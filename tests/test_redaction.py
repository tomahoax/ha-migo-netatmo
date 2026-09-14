"""Tests for the shared redaction helper.

The property that matters is completeness of SENSITIVE_KEYS, not the recursion:
the audit found the previous diagnostics redaction leaking because its key list
had drifted, not because it failed to descend. The recursion is still tested,
since the homesdata response nests everything sensitive under `homes[].rooms[]`,
`homes[].modules[]` and `homes[].schedules[].zones[]`.
"""

from __future__ import annotations

from custom_components.migo_netatmo.redact import REDACTED, SENSITIVE_KEYS, redact


def _leaked_keys(value: object, path: str = "") -> list[str]:
    """Return the path of every sensitive key still carrying its own value."""
    leaks: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else str(key)
            if key in SENSITIVE_KEYS and item != REDACTED:
                leaks.append(here)
            else:
                leaks.extend(_leaked_keys(item, here))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            leaks.extend(_leaked_keys(item, f"{path}[{i}]"))
    return leaks


class TestRedact:
    """Tests for redact()."""

    def test_redacts_a_top_level_key(self) -> None:
        """A sensitive key at the top level is replaced."""
        assert redact({"password": "hunter2"}) == {"password": REDACTED}

    def test_keeps_technical_identifiers(self) -> None:
        """Ids are deliberately preserved: support needs them, they locate nobody."""
        payload = {"id": "gateway_001", "home_id": "home_123", "type": "NAVaillant"}
        assert redact(payload) == payload

    def test_descends_into_lists_of_dicts(self) -> None:
        """Sensitive keys nested inside a list are redacted too."""
        payload = {"homes": [{"name": "Chez Dupont", "id": "home_123"}]}

        result = redact(payload)

        assert result["homes"][0]["name"] == REDACTED
        assert result["homes"][0]["id"] == "home_123"

    def test_descends_through_deeply_nested_lists(self) -> None:
        """homes[].schedules[].zones[].rooms[] is four levels of nesting."""
        payload = {
            "homes": [
                {
                    "schedules": [
                        {"name": "Default", "zones": [{"name": "Comfort", "id": 0}]},
                    ]
                }
            ]
        }

        result = redact(payload)

        schedule = result["homes"][0]["schedules"][0]
        assert schedule["name"] == REDACTED
        assert schedule["zones"][0]["name"] == REDACTED
        assert schedule["zones"][0]["id"] == 0

    def test_does_not_mutate_the_input(self) -> None:
        """Redaction must never damage the coordinator's own data."""
        payload = {"homes": [{"name": "Chez Dupont"}]}

        redact(payload)

        assert payload["homes"][0]["name"] == "Chez Dupont"

    def test_passes_scalars_through(self) -> None:
        """Non-container values are returned unchanged."""
        assert redact("plain") == "plain"
        assert redact(42) == 42
        assert redact(None) is None

    def test_redacts_a_realistic_homesdata_response(self) -> None:
        """End-to-end on the shape that actually leaked, checked exhaustively.

        These are the exact fields confirmed present thousands of times over in a
        real 102 MB debug log.
        """
        payload = {
            "body": {
                "user": {"email": "someone@example.com", "country": "FR"},
                "homes": [
                    {
                        "id": "home_123",
                        "name": "Chez Dupont",
                        "coordinates": [49.123456, 2.654321],
                        "city": "Somewhere",
                        "country": "FR",
                        "altitude": 120,
                        "timezone": "Europe/Paris",
                        "invitation_code": ["ZsdApbpjOstMdOn1"],
                        "rooms": [{"id": "room_456", "name": "Living Room"}],
                        "modules": [
                            {
                                "id": "gateway_001",
                                "oem_serial": "SN123456",
                                "boiler_id": "boiler_abc",
                            }
                        ],
                    }
                ],
            }
        }

        result = redact(payload)

        assert _leaked_keys(result) == []
        # And the parts support actually needs are still there.
        assert result["body"]["homes"][0]["id"] == "home_123"
        assert result["body"]["homes"][0]["modules"][0]["id"] == "gateway_001"


class TestSensitiveKeys:
    """Tests for the key list itself."""

    def test_covers_every_credential_field(self) -> None:
        """The config entry's own keys must all be sensitive."""
        for key in ("username", "password", "client_id", "client_secret", "user_prefix"):
            assert key in SENSITIVE_KEYS

    def test_covers_the_fields_confirmed_leaked(self) -> None:
        """Regression guard on the specific fields the audit found in the log."""
        for key in ("email", "coordinates", "city", "invitation_code", "oem_serial", "boiler_id"):
            assert key in SENSITIVE_KEYS

    def test_does_not_redact_identifiers(self) -> None:
        """Redacting ids would make diagnostics useless for support."""
        for key in ("id", "home_id", "device_id", "module_id", "room_id", "type", "bridge"):
            assert key not in SENSITIVE_KEYS
