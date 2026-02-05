"""DataUpdateCoordinator for UniFi Status."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SITE_ID,
    CONF_UNIFI_VERSION,
    DEFAULT_SITE,
    DEFAULT_UNIFI_VERSION,
    UPDATE_INTERVAL,
)
from .pyunifi.controller import APIError, Controller

_LOGGER = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 3


class UnifiStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching UniFi data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="UniFi Status",
            config_entry=config_entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.ctrl: Controller | None = None
        self._consecutive_failures = 0

    async def async_setup(self) -> None:
        """Create the controller connection."""
        await self._async_create_controller()

    async def _async_create_controller(self) -> None:
        """Create or recreate the controller connection."""
        data = self.config_entry.data
        # Close existing controller if any
        if self.ctrl is not None:
            try:
                await self.hass.async_add_executor_job(self.ctrl._logout_safe)
            except Exception:
                pass
        self.ctrl = await self.hass.async_add_executor_job(
            self._create_controller, data
        )
        self._consecutive_failures = 0

    @staticmethod
    def _create_controller(data: dict[str, Any]) -> Controller:
        """Create a Controller instance (runs in executor)."""
        return Controller(
            host=data[CONF_HOST],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            port=data.get(CONF_PORT, 8443),
            version=data.get(CONF_UNIFI_VERSION, DEFAULT_UNIFI_VERSION),
            site_id=data.get(CONF_SITE_ID, DEFAULT_SITE),
            ssl_verify=data.get(CONF_VERIFY_SSL, False),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the UniFi controller."""
        if self.ctrl is None:
            raise UpdateFailed("Controller not initialized")

        try:
            healthinfo, alerts, aps = await self.hass.async_add_executor_job(
                self._fetch_all
            )
            # Success - reset failure counter
            self._consecutive_failures = 0
        except APIError as err:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "UniFi API error (failure %d/%d): %s",
                self._consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                err,
            )

            # If too many consecutive failures, recreate the controller
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                _LOGGER.warning(
                    "Too many consecutive failures, recreating controller connection"
                )
                try:
                    await self._async_create_controller()
                    # Try one more time with the new controller
                    healthinfo, alerts, aps = await self.hass.async_add_executor_job(
                        self._fetch_all
                    )
                    self._consecutive_failures = 0
                except Exception as retry_err:
                    raise UpdateFailed(
                        f"Failed after controller recreation: {retry_err}"
                    ) from retry_err
            else:
                raise UpdateFailed(
                    f"Error communicating with UniFi controller: {err}"
                ) from err

        return {
            "healthinfo": healthinfo or [],
            "alerts": alerts or [],
            "aps": aps or [],
        }

    def _fetch_all(self) -> tuple[list, list, list]:
        """Fetch all data from the controller (runs in executor)."""
        healthinfo = self.ctrl.get_healthinfo()
        alerts = self.ctrl.get_alerts()
        aps = self.ctrl.get_aps()
        return healthinfo, alerts, aps
