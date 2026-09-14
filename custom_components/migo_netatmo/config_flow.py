"""Config flow for MiGO integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final, override

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import MigoApi, MigoApiError, MigoAuthError, MigoConnectionError
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_UPDATE_INTERVAL,
    CONF_USER_PREFIX,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
        vol.Optional(CONF_CLIENT_ID): TextSelector(),
        vol.Optional(CONF_CLIENT_SECRET): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Optional(CONF_USER_PREFIX): TextSelector(),
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_UPDATE_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Coerce(int),
        ),
    }
)


def _non_secret_suggestions(data: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the secret fields before they are suggested back to the browser.

    A suggested value is sent to the frontend over the websocket and sits in the
    page as a pre-filled form value. Pre-filling the stored password and client
    secret took them out of .storage and put them somewhere any script running in
    that origin could read: a compromised custom Lovelace card, an HACS frontend
    resource, a browser extension, or simply an unattended logged-in session. It
    also offered the MiGO password to the browser's password manager under Home
    Assistant's origin.

    The other fields are safe to pre-fill and are what makes the form usable.

    Args:
        data: Config entry data, or the user input being re-shown after an error.

    Returns:
        A copy without CONF_PASSWORD or CONF_CLIENT_SECRET.
    """
    return {k: v for k, v in data.items() if k not in _SECRET_FIELDS}


_SECRET_FIELDS: Final = frozenset({CONF_PASSWORD, CONF_CLIENT_SECRET})


class MigoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MiGO."""

    VERSION = 1

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> MigoOptionsFlow:
        """Get the options flow for this handler."""
        return MigoOptionsFlow()

    async def _async_validate_input(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Validate credentials against the API.

        Returns an errors dict for async_show_form; empty on success.
        """
        errors: dict[str, str] = {}
        api = MigoApi(
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            session=async_get_clientsession(self.hass),
            client_id=user_input.get(CONF_CLIENT_ID),
            client_secret=user_input.get(CONF_CLIENT_SECRET),
            user_prefix=user_input.get(CONF_USER_PREFIX),
        )
        try:
            await api.authenticate()
            homes_data = await api.get_homes_data()
            if not homes_data.get("body", {}).get("homes"):
                _LOGGER.warning("No homes found in MiGO account")
                errors["base"] = "no_homes"
        except MigoAuthError as err:
            _LOGGER.warning("Authentication failed: %s", err)
            errors["base"] = "invalid_auth"
        except MigoConnectionError as err:
            _LOGGER.warning("Cannot connect to the MiGO API: %s", err)
            errors["base"] = "cannot_connect"
        except MigoApiError as err:
            # The base class, so an HTTP 5xx from the API lands here rather than
            # in the catch-all below, which would show "unknown" plus a traceback.
            _LOGGER.warning("MiGO API returned an error: %s", err)
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception while validating credentials")
            errors["base"] = "unknown"

        # No api.close() here: the session is Home Assistant's shared one, so
        # this flow does not own it and must not close it.
        return errors

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Abort on duplicate accounts before any network call
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            errors = await self._async_validate_input(user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthorization."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle reauthorization confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            # Reauth must stay on the same account
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_mismatch()

            errors = await self._async_validate_input({**reauth_entry.data, **user_input})
            if not errors:
                return self.async_update_reload_and_abort(reauth_entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_REAUTH_DATA_SCHEMA,
                {CONF_USERNAME: reauth_entry.data.get(CONF_USERNAME)},
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            # Reconfigure must stay on the same account
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_mismatch()

            errors = await self._async_validate_input(user_input)
            if not errors:
                return self.async_update_reload_and_abort(reconfigure_entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                _non_secret_suggestions(user_input or reconfigure_entry.data),
            ),
            errors=errors,
        )


class MigoOptionsFlow(OptionsFlowWithReload):
    """Handle MiGO options (polling interval only).

    Credential changes go through the Reconfigure and Reauthenticate
    flows on the config entry.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, self.config_entry.options),
        )
