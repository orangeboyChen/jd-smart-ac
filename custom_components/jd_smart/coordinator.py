"""Coordinator for the JD Smart integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.components import persistent_notification
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .api import (
    JdSmartAuthError,
    JdSmartCannotConnectError,
    JdSmartClient,
    JdSmartError,
    JdSmartSnapshot,
    JdSmartTokenRefreshError,
)
from .const import (
    CONF_COOKIE,
    CONF_TGT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FAST_POLL_DURATION,
    FAST_POLL_INTERVAL,
    LOGGER,
    UPDATE_AUTH_FAILURE_THRESHOLD,
)

type JdSmartConfigEntry = ConfigEntry[JdSmartRuntimeData]


@dataclass
class JdSmartRuntimeData:
    """Runtime data for JD Smart."""

    client: JdSmartClient
    coordinators: dict[str, JdSmartCoordinator]


class JdSmartCoordinator(DataUpdateCoordinator[JdSmartSnapshot]):
    """Data coordinator for JD Smart."""

    config_entry: JdSmartConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: JdSmartConfigEntry,
        client: JdSmartClient,
        feed_id: str,
        device_name: str | None,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.feed_id = feed_id
        self.device_name = device_name
        self._fast_poll_cancel: Callable[[], None] | None = None
        self._token_refresh_lock = asyncio.Lock()
        self._consecutive_update_failures = 0

    async def _async_update_data(self) -> JdSmartSnapshot:
        """Fetch latest snapshot."""
        digest = self.data.digest if self.data else ""
        try:
            snapshot = await self.client.async_get_snapshot(self.feed_id, digest)
            self._consecutive_update_failures = 0
            return snapshot
        except JdSmartAuthError:
            LOGGER.info("JD Smart snapshot authentication failed; refreshing token")
            try:
                await self._async_refresh_token()
                snapshot = await self.client.async_get_snapshot(self.feed_id, digest)
                self._consecutive_update_failures = 0
                return snapshot
            except JdSmartAuthError as refresh_err:
                self._async_create_reauth_notification()
                raise ConfigEntryAuthFailed from refresh_err
            except JdSmartCannotConnectError as refresh_err:
                if self.data is None:
                    raise ConfigEntryNotReady from refresh_err
                await self._async_handle_update_failure(refresh_err)
            except JdSmartError as refresh_err:
                await self._async_handle_update_failure(refresh_err)
        except JdSmartCannotConnectError as err:
            if self.data is None:
                raise ConfigEntryNotReady from err
            await self._async_handle_update_failure(err)
        except JdSmartError as err:
            await self._async_handle_update_failure(err)
        raise UpdateFailed("Unable to update JD Smart")

    async def async_control_streams(self, commands: dict[str, object]) -> None:
        """Control streams and refresh state."""
        try:
            snapshot = await self.client.async_control_streams(self.feed_id, commands)
        except JdSmartAuthError as err:
            LOGGER.warning(
                "JD Smart control authentication failed: "
                "feed_id=%s, commands=%s, error=%s",
                self.feed_id,
                commands,
                err,
            )
            try:
                await self._async_refresh_token()
                snapshot = await self.client.async_control_streams(
                    self.feed_id,
                    commands,
                )
            except JdSmartAuthError as refresh_err:
                self._async_create_reauth_notification()
                raise ConfigEntryAuthFailed from refresh_err
            except JdSmartError as refresh_err:
                LOGGER.warning(
                    "JD Smart control failed after token refresh: "
                    "feed_id=%s, commands=%s, error=%s",
                    self.feed_id,
                    commands,
                    refresh_err,
                )
                raise UpdateFailed("Unable to control JD Smart") from refresh_err
        except JdSmartError as err:
            LOGGER.warning(
                "JD Smart control failed: feed_id=%s, commands=%s, error=%s",
                self.feed_id,
                commands,
                err,
            )
            raise UpdateFailed("Unable to control JD Smart") from err
        if snapshot is not None:
            self.async_set_updated_data(snapshot)
        self.trigger_fast_polling()
        await self.async_request_refresh()

    async def _async_refresh_token(self) -> None:
        """Refresh token and persist the refreshed values."""
        async with self._token_refresh_lock:
            try:
                new_tgt, new_cookie = await self.client.async_refresh_token()
            except JdSmartTokenRefreshError as err:
                LOGGER.exception("JD Smart token refresh failed")
                self._async_create_token_refresh_failed_notification(err)
                raise
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_TGT: new_tgt,
                    CONF_COOKIE: new_cookie,
                },
            )

    async def _async_handle_update_failure(self, err: JdSmartError) -> None:
        """Handle repeated update failures."""
        self._consecutive_update_failures += 1
        if self._consecutive_update_failures >= UPDATE_AUTH_FAILURE_THRESHOLD:
            LOGGER.warning(
                "JD Smart update failed repeatedly; requesting reauthentication: "
                "feed_id=%s, failures=%s",
                self.feed_id,
                self._consecutive_update_failures,
            )
            self._async_create_reauth_notification()
            raise ConfigEntryAuthFailed from err
        raise UpdateFailed("Unable to update JD Smart") from err

    @callback
    def _async_create_reauth_notification(self) -> None:
        """Create a persistent reauth notification."""
        persistent_notification.async_create(
            self.hass,
            (
                "JD Smart could not update the device data several times. "
                "Open Settings > Devices & services and reauthenticate JD Smart."
            ),
            title="JD Smart authentication required",
            notification_id=f"{DOMAIN}_{self.feed_id}_reauth",
        )

    @callback
    def _async_create_token_refresh_failed_notification(self, err: Exception) -> None:
        """Create a persistent notification for token refresh failures."""
        reason = str(err) or err.__class__.__name__
        persistent_notification.async_create(
            self.hass,
            (
                "JD Smart failed to refresh authentication. "
                f"Device: {self.device_name or self.feed_id}. "
                f"Reason: {reason}. "
                "Open Settings > Devices & services and update JD Smart authentication."
            ),
            title="JD Smart authentication refresh failed",
            notification_id=f"{DOMAIN}_{self.feed_id}_token_refresh_failed",
        )

    def async_shutdown(self) -> None:
        """Cancel pending coordinator callbacks."""
        if self._fast_poll_cancel:
            self._fast_poll_cancel()
            self._fast_poll_cancel = None

    @callback
    def trigger_fast_polling(self) -> None:
        """Temporarily poll faster after a control command."""
        self.update_interval = FAST_POLL_INTERVAL
        if self._fast_poll_cancel:
            self._fast_poll_cancel()
        end = dt_util.utcnow() + FAST_POLL_DURATION
        self._fast_poll_cancel = async_track_point_in_utc_time(
            self.hass, self._reset_polling, end
        )

    @callback
    def _reset_polling(self, _now: datetime) -> None:
        """Reset polling interval."""
        self.update_interval = DEFAULT_SCAN_INTERVAL
        self._fast_poll_cancel = None
