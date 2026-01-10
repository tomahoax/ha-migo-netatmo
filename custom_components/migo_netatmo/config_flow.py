"""Config flow for MiGO integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import MigoApi, MigoAuthError
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
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_CLIENT_ID): str,
        vol.Optional(CONF_CLIENT_SECRET): str,
        vol.Optional(CONF_USER_PREFIX): str,
    }
)


class MigoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MiGO."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MigoOptionsFlow:
        """Get the options flow for this handler."""
        return MigoOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Starting MiGO configuration flow")
            try:
                # Test authentication
                _LOGGER.debug("Testing credentials for user: %s", user_input[CONF_USERNAME])
                api = MigoApi(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    client_id=user_input.get(CONF_CLIENT_ID),
                    client_secret=user_input.get(CONF_CLIENT_SECRET),
                )
                await api.authenticate()
                _LOGGER.debug("Authentication successful")

                # Get homes data to verify access
                _LOGGER.debug("Fetching homes data to verify access")
                homes_data = await api.get_homes_data()
                await api.close()

                if "body" not in homes_data or not homes_data["body"].get("homes"):
                    _LOGGER.warning("No homes found in MiGO account")
                    errors["base"] = "no_homes"
                else:
                    homes = homes_data["body"]["homes"]
                    _LOGGER.debug("Found %d homes in account", len(homes))

                    # Use email as unique ID
                    await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                    self._abort_if_unique_id_configured()

                    _LOGGER.info(
                        "MiGO integration configured successfully for %s",
                        user_input[CONF_USERNAME],
                    )
                    return self.async_create_entry(
                        title=user_input[CONF_USERNAME],
                        data=user_input,
                    )

            except MigoAuthError as err:
                _LOGGER.warning("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during configuration")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauthorization."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reauthorization confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Starting MiGO re-authentication flow")
            try:
                _LOGGER.debug("Testing credentials for user: %s", user_input[CONF_USERNAME])
                api = MigoApi(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    client_id=user_input.get(CONF_CLIENT_ID),
                    client_secret=user_input.get(CONF_CLIENT_SECRET),
                )
                await api.authenticate()
                await api.close()
                _LOGGER.debug("Re-authentication successful")

                # Update the config entry
                self.hass.config_entries.async_update_entry(
                    self._get_reauth_entry(),
                    data=user_input,
                )
                await self.hass.config_entries.async_reload(self._get_reauth_entry().entry_id)
                _LOGGER.info(
                    "MiGO integration re-authenticated successfully for %s",
                    user_input[CONF_USERNAME],
                )
                return self.async_abort(reason="reauth_successful")

            except MigoAuthError as err:
                _LOGGER.warning("Re-authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during re-authentication")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class MigoOptionsFlow(config_entries.OptionsFlow):
    """Handle MiGo options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Updating MiGO options: %s", user_input)

            # Check if credentials changed - if so, validate them
            credentials_changed = (
                user_input.get(CONF_USERNAME) != self.config_entry.data.get(CONF_USERNAME)
                or user_input.get(CONF_PASSWORD) != self.config_entry.data.get(CONF_PASSWORD)
                or user_input.get(CONF_CLIENT_ID) != self.config_entry.data.get(CONF_CLIENT_ID)
                or user_input.get(CONF_CLIENT_SECRET) != self.config_entry.data.get(CONF_CLIENT_SECRET)
                or user_input.get(CONF_USER_PREFIX) != self.config_entry.data.get(CONF_USER_PREFIX)
            )

            if credentials_changed:
                # Test new credentials
                try:
                    api = MigoApi(
                        username=user_input[CONF_USERNAME],
                        password=user_input[CONF_PASSWORD],
                        client_id=user_input.get(CONF_CLIENT_ID),
                        client_secret=user_input.get(CONF_CLIENT_SECRET),
                        user_prefix=user_input.get(CONF_USER_PREFIX),
                    )
                    await api.authenticate()
                    await api.close()
                    _LOGGER.debug("New credentials validated successfully")
                except MigoAuthError as err:
                    _LOGGER.warning("New credentials validation failed: %s", err)
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected error validating new credentials")
                    errors["base"] = "unknown"

            if not errors:
                # Separate data and options
                new_data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                if user_input.get(CONF_CLIENT_ID):
                    new_data[CONF_CLIENT_ID] = user_input[CONF_CLIENT_ID]
                if user_input.get(CONF_CLIENT_SECRET):
                    new_data[CONF_CLIENT_SECRET] = user_input[CONF_CLIENT_SECRET]
                if user_input.get(CONF_USER_PREFIX):
                    new_data[CONF_USER_PREFIX] = user_input[CONF_USER_PREFIX]

                new_options = {
                    CONF_UPDATE_INTERVAL: user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                }

                # Update the config entry data if credentials changed
                if credentials_changed:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data,
                    )

                return self.async_create_entry(title="", data=new_options)

        # Build form with current values
        current_data = self.config_entry.data
        current_options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=current_data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(
                        CONF_PASSWORD,
                        default=current_data.get(CONF_PASSWORD, ""),
                    ): str,
                    vol.Optional(
                        CONF_CLIENT_ID,
                        description={"suggested_value": current_data.get(CONF_CLIENT_ID, "")},
                    ): str,
                    vol.Optional(
                        CONF_CLIENT_SECRET,
                        description={"suggested_value": current_data.get(CONF_CLIENT_SECRET, "")},
                    ): str,
                    vol.Optional(
                        CONF_USER_PREFIX,
                        description={"suggested_value": current_data.get(CONF_USER_PREFIX, "")},
                    ): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=current_options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                    ),
                }
            ),
            errors=errors,
        )
