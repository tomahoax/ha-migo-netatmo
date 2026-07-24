"""Tests for pure helper utilities in helpers.py."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.migo_netatmo.helpers import (
    calculate_signal_quality,
    format_mac_address,
    generate_unique_id,
    get_device_name,
    get_devices_by_type,
    get_gateway_mac_for_home,
    get_home_id_or_raise,
    get_thermostat_for_room,
    parse_api_response,
    safe_float,
    safe_get,
    safe_int,
)


class TestSafeGet:
    """Tests for safe_get."""

    def test_returns_none_data_default(self) -> None:
        """A None root mapping returns the default without traversing."""
        assert safe_get(None, "body") is None
        assert safe_get(None, "body", default="fallback") == "fallback"

    def test_traverses_nested_keys(self) -> None:
        """Nested keys are followed in order."""
        data = {"body": {"home": {"id": "123"}}}
        assert safe_get(data, "body", "home", "id") == "123"

    def test_missing_key_returns_default(self) -> None:
        """A missing key anywhere along the path returns the default."""
        data = {"body": {"home": {"id": "123"}}}
        assert safe_get(data, "body", "missing", "key", default="N/A") == "N/A"

    def test_non_dict_intermediate_returns_default(self) -> None:
        """Hitting a non-dict value before exhausting keys returns the default."""
        data = {"body": "not_a_dict"}
        assert safe_get(data, "body", "home", default="N/A") == "N/A"

    def test_no_keys_returns_data_itself(self) -> None:
        """With no keys to traverse, the mapping itself is returned."""
        data = {"a": 1}
        assert safe_get(data) == data


class TestParseApiResponse:
    """Tests for parse_api_response."""

    def test_valid_response_returns_body(self) -> None:
        """A well-formed response returns its body dict."""
        response = {"body": {"home": {"id": "123"}}, "status": "ok"}
        assert parse_api_response(response) == {"home": {"id": "123"}}

    def test_non_dict_response_raises(self) -> None:
        """A non-dict response raises ValueError."""
        with pytest.raises(ValueError, match="Invalid response type"):
            parse_api_response("not a dict")  # type: ignore[arg-type]

    def test_missing_body_raises(self) -> None:
        """A response without a 'body' key raises ValueError."""
        with pytest.raises(ValueError, match="missing 'body'"):
            parse_api_response({"status": "ok"})

    def test_missing_required_key_raises(self) -> None:
        """A body missing the caller-required key raises ValueError."""
        with pytest.raises(ValueError, match="missing required key"):
            parse_api_response({"body": {"home": {}}}, required_key="rooms")

    def test_required_key_present_passes(self) -> None:
        """The required-key check passes when the key exists in the body."""
        body = parse_api_response({"body": {"rooms": []}}, required_key="rooms")
        assert body == {"rooms": []}


class TestSafeFloat:
    """Tests for safe_float."""

    def test_none_returns_default(self) -> None:
        """None input returns the default unchanged."""
        assert safe_float(None) is None
        assert safe_float(None, default=1.0) == 1.0

    def test_valid_values_convert(self) -> None:
        """Numeric strings and numbers convert to float."""
        assert safe_float("21.5") == 21.5
        assert safe_float(20) == 20.0

    def test_invalid_value_returns_default(self) -> None:
        """A non-numeric value falls back to the default."""
        assert safe_float("not_a_number") is None
        assert safe_float("not_a_number", default=0.0) == 0.0

    def test_invalid_type_returns_default(self) -> None:
        """A value that can't be coerced to float falls back to the default."""
        assert safe_float(object(), default=-1.0) == -1.0


class TestSafeInt:
    """Tests for safe_int."""

    def test_none_returns_default(self) -> None:
        """None input returns the default unchanged."""
        assert safe_int(None) is None
        assert safe_int(None, default=5) == 5

    def test_valid_values_convert(self) -> None:
        """Numeric strings and floats convert to int."""
        assert safe_int("42") == 42
        assert safe_int(3.9) == 3

    def test_invalid_value_returns_default(self) -> None:
        """A non-numeric value falls back to the default."""
        assert safe_int("not_a_number") is None
        assert safe_int("not_a_number", default=0) == 0


class TestFormatMacAddress:
    """Tests for format_mac_address."""

    def test_colon_separated_input(self) -> None:
        """An already colon-separated MAC is normalized to uppercase."""
        assert format_mac_address("70:ee:50:6b:e3:6a") == "70:EE:50:6B:E3:6A"

    def test_dash_separated_input(self) -> None:
        """A dash-separated MAC is reformatted with colons."""
        assert format_mac_address("70-ee-50-6b-e3-6a") == "70:EE:50:6B:E3:6A"

    def test_bare_input(self) -> None:
        """A MAC with no separators gets colons inserted every 2 characters."""
        assert format_mac_address("70ee506be36a") == "70:EE:50:6B:E3:6A"


class TestGetDeviceName:
    """Tests for get_device_name."""

    def test_long_id_uses_last_four_characters(self) -> None:
        """A long device ID is shortened to its last 4 characters."""
        assert get_device_name({"id": "70:ee:50:6b:e3:6a"}, "Gateway") == "Gateway 3:6a"

    def test_short_id_used_as_is(self) -> None:
        """An ID shorter than 4 characters is used unchanged."""
        assert get_device_name({"id": "a1"}, "Gateway") == "Gateway a1"

    def test_missing_id_truncates_the_unknown_fallback(self) -> None:
        """A device without an 'id' falls back to 'Unknown', truncated to 4 chars.

        The truncation is applied to the fallback sentinel as well as to a real
        ID, which is why the result reads oddly.
        """
        assert get_device_name({}, "Gateway") == f"Gateway {'Unknown'[-4:]}"


class TestCalculateSignalQuality:
    """Tests for calculate_signal_quality."""

    THRESHOLDS = (80, 60, 40)

    def test_none_strength_returns_none(self) -> None:
        """No signal reading returns None."""
        assert calculate_signal_quality(None, self.THRESHOLDS) is None

    @pytest.mark.parametrize(
        ("strength", "expected"),
        [
            (90, "excellent"),
            (80, "excellent"),
            (70, "good"),
            (60, "good"),
            (50, "fair"),
            (40, "fair"),
            (10, "poor"),
        ],
    )
    def test_thresholds(self, strength: int, expected: str) -> None:
        """Each boundary maps to the expected quality label."""
        assert calculate_signal_quality(strength, self.THRESHOLDS) == expected


class TestGenerateUniqueId:
    """Tests for generate_unique_id."""

    def test_format(self) -> None:
        """The unique ID follows the migo_netatmo_{type}_{id} convention."""
        assert generate_unique_id("temp", "room_456") == "migo_netatmo_temp_room_456"


def _make_coordinator(
    devices: dict[str, dict[str, Any]] | None = None,
    rooms: dict[str, dict[str, Any]] | None = None,
) -> Any:
    """Build a minimal stand-in exposing the .devices/.rooms attributes these helpers read."""
    return SimpleNamespace(devices=devices or {}, rooms=rooms or {})


class TestGetDevicesByType:
    """Tests for get_devices_by_type."""

    def test_filters_by_type(self) -> None:
        """Only devices matching the requested type are returned."""
        coordinator = _make_coordinator(
            devices={
                "gw1": {"type": "NAVaillant"},
                "therm1": {"type": "NAThermVaillant"},
                "therm2": {"type": "NAThermVaillant"},
            }
        )
        result = get_devices_by_type(coordinator, "NAThermVaillant")
        assert set(result) == {"therm1", "therm2"}

    def test_no_match_returns_empty_dict(self) -> None:
        """No devices of the requested type returns an empty dict."""
        coordinator = _make_coordinator(devices={"gw1": {"type": "NAVaillant"}})
        assert get_devices_by_type(coordinator, "Unknown") == {}


class TestGetHomeIdOrRaise:
    """Tests for get_home_id_or_raise."""

    def test_returns_home_id_when_present(self) -> None:
        """A data dict with home_id returns it unchanged."""
        assert get_home_id_or_raise({"home_id": "home_123"}, "room", "room_456") == "home_123"

    def test_raises_when_missing(self) -> None:
        """A data dict without home_id raises a translated HomeAssistantError."""
        with pytest.raises(HomeAssistantError):
            get_home_id_or_raise({}, "room", "room_456")


class TestGetGatewayMacForHome:
    """Tests for get_gateway_mac_for_home."""

    def test_finds_matching_gateway(self) -> None:
        """The gateway device ID for the given home is returned."""
        coordinator = _make_coordinator(
            devices={
                "70:ee:50:6b:e3:6a": {"type": "NAVaillant", "home_id": "home_123"},
                "other_gw": {"type": "NAVaillant", "home_id": "home_999"},
            }
        )
        assert get_gateway_mac_for_home(coordinator, "home_123") == "70:ee:50:6b:e3:6a"

    def test_no_match_returns_none(self) -> None:
        """No gateway for the given home returns None."""
        coordinator = _make_coordinator(devices={})
        assert get_gateway_mac_for_home(coordinator, "home_123") is None


class TestGetThermostatForRoom:
    """Tests for get_thermostat_for_room."""

    def test_finds_thermostat_via_module_ids(self) -> None:
        """The thermostat module linked to the room is returned."""
        coordinator = _make_coordinator(
            devices={"therm1": {"type": "NAThermVaillant"}},
            rooms={"room_456": {"module_ids": ["therm1"]}},
        )
        assert get_thermostat_for_room(coordinator, "room_456") == "therm1"

    def test_no_module_ids_returns_none(self) -> None:
        """A room without module_ids returns None."""
        coordinator = _make_coordinator(rooms={"room_456": {}})
        assert get_thermostat_for_room(coordinator, "room_456") is None

    def test_module_not_a_thermostat_returns_none(self) -> None:
        """A linked module that isn't a thermostat type returns None."""
        coordinator = _make_coordinator(
            devices={"gw1": {"type": "NAVaillant"}},
            rooms={"room_456": {"module_ids": ["gw1"]}},
        )
        assert get_thermostat_for_room(coordinator, "room_456") is None
