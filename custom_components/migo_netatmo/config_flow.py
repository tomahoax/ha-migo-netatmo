"""Config flow for MiGO integration."""

from __future__ import annotations

import logging
from typing import Any, override

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

from .api import MigoApi, MigoAuthError, MigoConnectionError
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
                user_input or reconfigure_entry.data,
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
