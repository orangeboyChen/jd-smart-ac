"""The JD Smart integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JdSmartCredentials, JdSmartDeviceProfile, JdSmartClient
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
)
from .coordinator import JdSmartConfigEntry, JdSmartCoordinator, JdSmartRuntimeData

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: JdSmartConfigEntry) -> bool:
    """Set up JD Smart from a config entry."""
    client = JdSmartClient(
        async_get_clientsession(hass),
        JdSmartCredentials(
            cookie=entry.data[CONF_COOKIE],
            tgt=entry.data[CONF_TGT],
            pin=entry.data.get(CONF_PIN),
            sgm_context=entry.data.get(CONF_SGM_CONTEXT),
        ),
        JdSmartDeviceProfile(
            device_id=entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
            app_version=entry.data.get(CONF_APP_VERSION, DEFAULT_APP_VERSION),
            platform=entry.data.get(CONF_PLATFORM, DEFAULT_PLATFORM),
            device_model=entry.data.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL),
            platform_version=entry.data.get(
                CONF_PLATFORM_VERSION, DEFAULT_PLATFORM_VERSION
            ),
            channel=entry.data.get(CONF_CHANNEL, DEFAULT_CHANNEL),
            user_agent=entry.data.get(CONF_USER_AGENT, DEFAULT_USER_AGENT),
        ),
    )
    coordinator = JdSmartCoordinator(hass, entry, client, entry.data[CONF_FEED_ID])
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = JdSmartRuntimeData(
        client=client,
        coordinator=coordinator,
        feed_id=entry.data[CONF_FEED_ID],
        device_name=entry.data.get(CONF_DEVICE_NAME),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JdSmartConfigEntry) -> bool:
    """Unload a config entry."""
    if runtime_data := getattr(entry, "runtime_data", None):
        runtime_data.coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: JdSmartConfigEntry) -> bool:
    """Reload a config entry."""
    if not await async_unload_entry(hass, entry):
        return False
    return await async_setup_entry(hass, entry)
