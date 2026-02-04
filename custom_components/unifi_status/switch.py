"""Switch platform for UniFi Status."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiStatusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Status switches from a config entry."""
    coordinator: UnifiStatusCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []

    for device in coordinator.data.get("aps", []):
        device_name = device.get("name") or device.get("ip", "unknown")
        device_id = device["device_id"]

        # Restart switch for every device
        entities.append(UnifiRestartSwitch(coordinator, entry, device_id, device_name))

        # PoE port switches
        for port in device.get("port_table", []):
            if port.get("port_poe"):
                entities.append(
                    UnifiPoESwitch(
                        coordinator,
                        entry,
                        device_id,
                        device_name,
                        port["port_idx"],
                        port.get("name", f"Port {port['port_idx']}"),
                    )
                )

    async_add_entities(entities)


def _get_device(
    coordinator: UnifiStatusCoordinator, device_id: str
) -> dict[str, Any] | None:
    """Find a device by device_id in coordinator data."""
    for device in coordinator.data.get("aps", []):
        if device.get("device_id") == device_id:
            return device
    return None


def _device_info_for_ap(
    entry: ConfigEntry, device: dict[str, Any], device_name: str
) -> DeviceInfo:
    """Build DeviceInfo for a network device, linked to the controller."""
    return DeviceInfo(
        identifiers={(DOMAIN, device.get("mac", device.get("device_id")))},
        name=device_name,
        manufacturer="Ubiquiti",
        model=device.get("model"),
        sw_version=device.get("version"),
        via_device=(DOMAIN, entry.entry_id),
    )


class UnifiRestartSwitch(CoordinatorEntity[UnifiStatusCoordinator], SwitchEntity):
    """Switch to restart a UniFi device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiStatusCoordinator,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the restart switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._device_name = device_name
        self._attr_name = "Restart"
        self._attr_unique_id = f"{entry.entry_id}_restart_{device_id}"
        self._attr_icon = "mdi:restart"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this AP."""
        device = _get_device(self.coordinator, self._device_id)
        if device:
            return _device_info_for_ap(self._entry, device, self._device_name)
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Ubiquiti",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def is_on(self) -> bool | None:
        """Return false — restart is a momentary action, device is never 'on'."""
        device = _get_device(self.coordinator, self._device_id)
        if device is None:
            return None
        # state 1=connected, 4=upgrading, 5=provisioning, 6=heartbeat missed
        return device.get("state") in (1, 4, 5, 6)

    @property
    def available(self) -> bool:
        """Return True if the device exists in coordinator data."""
        return (
            super().available
            and _get_device(self.coordinator, self._device_id) is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device attributes."""
        device = _get_device(self.coordinator, self._device_id)
        if device is None:
            return {}
        attrs: dict[str, Any] = {}
        for key in ("model", "serial", "version", "ip", "mac", "uptime"):
            if key in device:
                attrs[key] = device[key]
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Restart the device."""
        device = _get_device(self.coordinator, self._device_id)
        if device is None:
            return
        mac = device["mac"]
        await self.hass.async_add_executor_job(self.coordinator.ctrl.restart_ap, mac)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """No-op — cannot 'un-restart' a device."""


class UnifiPoESwitch(CoordinatorEntity[UnifiStatusCoordinator], SwitchEntity):
    """Switch to control PoE power on a port."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiStatusCoordinator,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
        port_idx: int,
        port_name: str,
    ) -> None:
        """Initialize the PoE switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._device_name = device_name
        self._port_idx = port_idx
        self._attr_name = f"PoE {port_name}"
        self._attr_unique_id = f"{entry.entry_id}_poe_{device_id}_{port_idx}"
        self._attr_icon = "mdi:ethernet"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this AP."""
        device = _get_device(self.coordinator, self._device_id)
        if device:
            return _device_info_for_ap(self._entry, device, self._device_name)
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Ubiquiti",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    def _get_port(self) -> dict[str, Any] | None:
        """Get the port dict from coordinator data."""
        device = _get_device(self.coordinator, self._device_id)
        if device is None:
            return None
        for port in device.get("port_table", []):
            if port.get("port_idx") == self._port_idx:
                return port
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if PoE is enabled (mode=auto) on this port."""
        port = self._get_port()
        if port is None:
            return None
        return port.get("poe_mode") == "auto"

    @property
    def available(self) -> bool:
        """Return True if the device and port exist in coordinator data."""
        if not super().available:
            return False
        device = _get_device(self.coordinator, self._device_id)
        if device is None or device.get("state") not in (1, 4, 5, 6):
            return False
        return self._get_port() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return PoE port attributes."""
        port = self._get_port()
        if port is None:
            return {}
        attrs: dict[str, Any] = {}
        for key in ("poe_voltage", "poe_current", "poe_power"):
            if key in port:
                attrs[key] = port[key]
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PoE on this port."""
        device = _get_device(self.coordinator, self._device_id)
        if device is None:
            return
        mac = device["mac"]
        await self.hass.async_add_executor_job(
            self.coordinator.ctrl.switch_port_power_on, mac, self._port_idx
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PoE on this port."""
        device = _get_device(self.coordinator, self._device_id)
        if device is None:
            return
        mac = device["mac"]
        await self.hass.async_add_executor_job(
            self.coordinator.ctrl.switch_port_power_off, mac, self._port_idx
        )
        await self.coordinator.async_request_refresh()
