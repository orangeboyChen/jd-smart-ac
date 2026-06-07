"""Coordinator for the JD Smart integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
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
)

type JdSmartConfigEntry = ConfigEntry[JdSmartRuntimeData]


@dataclass
class JdSmartRuntimeData:
    """Runtime data for JD Smart."""

    client: JdSmartClient
    coordinator: JdSmartCoordinator
    feed_id: str


class JdSmartCoordinator(DataUpdateCoordinator[JdSmartSnapshot]):
    """Data coordinator for JD Smart."""

    config_entry: JdSmartConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: JdSmartConfigEntry,
        client: JdSmartClient,
        feed_id: str,
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
        self._fast_poll_cancel: Callable[[], None] | None = None
        self._token_refresh_lock = asyncio.Lock()

    async def _async_update_data(self) -> JdSmartSnapshot:
        """Fetch latest snapshot."""
        digest = self.data.digest if self.data else ""
        try:
            return await self.client.async_get_snapshot(self.feed_id, digest)
        except JdSmartAuthError as err:
            LOGGER.info("JD Smart snapshot authentication failed; refreshing token")
            try:
                await self._async_refresh_token()
                return await self.client.async_get_snapshot(self.feed_id, digest)
            except JdSmartAuthError as refresh_err:
                raise ConfigEntryAuthFailed from refresh_err
            except JdSmartCannotConnectError as refresh_err:
                if self.data is None:
                    raise ConfigEntryNotReady from refresh_err
                raise UpdateFailed("Unable to update JD Smart") from refresh_err
            except JdSmartError as refresh_err:
                raise UpdateFailed("Unable to update JD Smart") from refresh_err
        except JdSmartCannotConnectError as err:
            if self.data is None:
                raise ConfigEntryNotReady from err
            raise UpdateFailed("Unable to update JD Smart") from err
        except JdSmartError as err:
            raise UpdateFailed("Unable to update JD Smart") from err

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
            except JdSmartTokenRefreshError:
                LOGGER.exception("JD Smart token refresh failed")
                raise
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_TGT: new_tgt,
                    CONF_COOKIE: new_cookie,
                },
            )

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
