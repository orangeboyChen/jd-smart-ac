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
    JdSmartDevice,
    JdSmartDeviceProfile,
    JdSmartError,
)
from .const import (
    CONF_APP_VERSION,
    CONF_CHANNEL,
    CONF_COOKIE,
    CONF_DEVICE_NAME,
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
    DEFAULT_DEVICE_ID,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_PLATFORM,
    DEFAULT_PLATFORM_VERSION,
    DEFAULT_USER_AGENT,
    DOMAIN,
    LOGGER,
)

CONF_SELECTED_DEVICE = "selected_device"


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return config schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
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
    data.setdefault(CONF_DEVICE_ID, DEFAULT_DEVICE_ID or str(secrets.randbelow(10**20)))
    data.setdefault(CONF_PLATFORM, DEFAULT_PLATFORM)
    data.setdefault(CONF_APP_VERSION, DEFAULT_APP_VERSION)
    data.setdefault(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL)
    data.setdefault(CONF_PLATFORM_VERSION, DEFAULT_PLATFORM_VERSION)
    data.setdefault(CONF_CHANNEL, DEFAULT_CHANNEL)
    data.setdefault(CONF_USER_AGENT, DEFAULT_USER_AGENT)
    return data


def _client_from_data(hass: HomeAssistant, data: dict[str, Any]) -> JdSmartClient:
    """Build an API client from config flow data."""
    return JdSmartClient(
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


async def _fetch_devices(
    hass: HomeAssistant, data: dict[str, Any]
) -> list[JdSmartDevice]:
    """Validate auth by fetching selectable devices."""
    client = _client_from_data(hass, data)
    try:
        return await client.async_get_devices()
    except JdSmartAuthError:
        LOGGER.info("JD Smart device-list auth failed; refreshing token")
        new_tgt, new_cookie = await client.async_refresh_token()
        data[CONF_TGT] = new_tgt
        data[CONF_COOKIE] = new_cookie
        return await client.async_get_devices()


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate input by fetching a snapshot."""
    client = _client_from_data(hass, data)
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
    _auth_data: dict[str, Any]
    _devices: list[JdSmartDevice]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean_input(user_input)
            try:
                devices = await _fetch_devices(self.hass, data)
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
                self._auth_data = data
                self._devices = devices
                return await self.async_step_select_device()

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection."""
        errors: dict[str, str] = {}
        devices = getattr(self, "_devices", [])
        if user_input is not None:
            feed_id = user_input[CONF_SELECTED_DEVICE]
            device = next(
                (item for item in devices if item.feed_id == feed_id),
                None,
            )
            if device is None:
                errors["base"] = "unknown"
            else:
                data = {
                    **self._auth_data,
                    CONF_FEED_ID: device.feed_id,
                    CONF_DEVICE_NAME: device.name,
                }
                await self.async_set_unique_id(device.feed_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=device.name, data=data)

        choices = {device.feed_id: _device_label(device) for device in devices}
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({vol.Required(CONF_SELECTED_DEVICE): vol.In(choices)}),
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
            data = {**entry.data, **_clean_input(user_input)}
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


def _device_label(device: JdSmartDevice) -> str:
    """Return a readable device option label."""
    details = [value for value in (device.room_name, device.category_name) if value]
    suffix = f" - {' / '.join(details)}" if details else ""
    return f"{device.name}{suffix} ({device.feed_id})"
