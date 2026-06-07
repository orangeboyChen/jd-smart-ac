"""Config flow for JD Smart."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    JdSmartAuthError,
    JdSmartCannotConnectError,
    JdSmartClient,
    JdSmartCredentials,
    JdSmartDeviceProfile,
    JdSmartError,
)
from .const import (
    CONF_APP_VERSION,
    CONF_CHANNEL,
    CONF_COOKIE,
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_FEED_ID,
    CONF_PLATFORM,
    CONF_PLATFORM_VERSION,
    CONF_PIN,
    CONF_SGM_CONTEXT,
    CONF_TGT,
    CONF_USER_AGENT,
    DEFAULT_APP_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_PLATFORM,
    DEFAULT_PLATFORM_VERSION,
    DEFAULT_USER_AGENT,
    DOMAIN,
    LOGGER,
)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return config schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_FEED_ID, default=defaults.get(CONF_FEED_ID, "")): str,
            vol.Required(CONF_COOKIE, default=defaults.get(CONF_COOKIE, "")): str,
            vol.Required(CONF_TGT, default=defaults.get(CONF_TGT, "")): str,
            vol.Optional(CONF_PIN, default=defaults.get(CONF_PIN, "")): str,
            vol.Optional(
                CONF_SGM_CONTEXT, default=defaults.get(CONF_SGM_CONTEXT, "")
            ): str,
            vol.Optional(
                CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, "")
            ): str,
            vol.Optional(
                CONF_PLATFORM, default=defaults.get(CONF_PLATFORM, DEFAULT_PLATFORM)
            ): str,
            vol.Optional(
                CONF_APP_VERSION,
                default=defaults.get(CONF_APP_VERSION, DEFAULT_APP_VERSION),
            ): str,
            vol.Optional(
                CONF_DEVICE_MODEL,
                default=defaults.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL),
            ): str,
            vol.Optional(
                CONF_PLATFORM_VERSION,
                default=defaults.get(
                    CONF_PLATFORM_VERSION, DEFAULT_PLATFORM_VERSION
                ),
            ): str,
            vol.Optional(
                CONF_CHANNEL, default=defaults.get(CONF_CHANNEL, DEFAULT_CHANNEL)
            ): str,
            vol.Optional(
                CONF_USER_AGENT,
                default=defaults.get(CONF_USER_AGENT, DEFAULT_USER_AGENT),
            ): str,
        }
    )


def _clean_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Clean user input and fill defaults."""
    data = {key: value for key, value in user_input.items() if value != ""}
    data.setdefault(CONF_DEVICE_ID, str(secrets.randbelow(10**20)))
    data.setdefault(CONF_PLATFORM, DEFAULT_PLATFORM)
    data.setdefault(CONF_APP_VERSION, DEFAULT_APP_VERSION)
    data.setdefault(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL)
    data.setdefault(CONF_PLATFORM_VERSION, DEFAULT_PLATFORM_VERSION)
    data.setdefault(CONF_CHANNEL, DEFAULT_CHANNEL)
    data.setdefault(CONF_USER_AGENT, DEFAULT_USER_AGENT)
    return data


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate input by fetching a snapshot."""
    client = JdSmartClient(
        async_get_clientsession(hass),
        JdSmartCredentials(
            cookie=data[CONF_COOKIE],
            tgt=data[CONF_TGT],
            pin=data.get(CONF_PIN),
            sgm_context=data.get(CONF_SGM_CONTEXT),
        ),
        JdSmartDeviceProfile(
            device_id=data[CONF_DEVICE_ID],
            app_version=data[CONF_APP_VERSION],
            platform=data[CONF_PLATFORM],
            device_model=data[CONF_DEVICE_MODEL],
            platform_version=data[CONF_PLATFORM_VERSION],
            channel=data[CONF_CHANNEL],
            user_agent=data[CONF_USER_AGENT],
        ),
    )
    try:
        await client.async_get_snapshot(data[CONF_FEED_ID])
    except JdSmartAuthError:
        LOGGER.info("JD Smart config validation auth failed; refreshing token")
        new_tgt, new_cookie = await client.async_refresh_token()
        data[CONF_TGT] = new_tgt
        data[CONF_COOKIE] = new_cookie
        await client.async_get_snapshot(data[CONF_FEED_ID])


class JdSmartAcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JD Smart."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean_input(user_input)
            self._async_abort_entries_match({CONF_FEED_ID: data[CONF_FEED_ID]})
            try:
                await _validate_input(self.hass, data)
            except JdSmartAuthError:
                errors["base"] = "invalid_auth"
            except JdSmartCannotConnectError:
                errors["base"] = "cannot_connect"
            except JdSmartError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(data[CONF_FEED_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"JD Smart {data[CONF_FEED_ID]}",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean_input({**entry.data, **user_input})
            try:
                await _validate_input(self.hass, data)
            except JdSmartAuthError:
                errors["base"] = "invalid_auth"
            except JdSmartError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(entry.data),
            errors=errors,
        )
