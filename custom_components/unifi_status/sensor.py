"""Sensor platform for UniFi Status."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MONITORED_CONDITIONS,
    DEFAULT_MONITORED,
    DOMAIN,
    SENSOR_ALERTS,
    SENSOR_FIRMWARE,
    SENSOR_LAN,
    SENSOR_VPN,
    SENSOR_WAN,
    SENSOR_WLAN,
    SENSOR_WWW,
)
from .coordinator import UnifiStatusCoordinator

_LOGGER = logging.getLogger(__name__)

USG_SENSORS: dict[str, list[str]] = {
    SENSOR_VPN: ["VPN", "", "mdi:folder-key-network"],
    SENSOR_WWW: ["WWW", "", "mdi:web"],
    SENSOR_WAN: ["WAN", "", "mdi:shield-outline"],
    SENSOR_LAN: ["LAN", "", "mdi:lan"],
    SENSOR_WLAN: ["WLAN", "", "mdi:wifi"],
    SENSOR_ALERTS: ["Alerts", "", "mdi:information-outline"],
    SENSOR_FIRMWARE: ["Firmware Upgradable", "", "mdi:database-plus"],
}


def _format_uptime(seconds: int | float) -> str:
    """Format an uptime value in seconds to a human-readable string."""
    time_val = int(seconds)
    if time_val < 60:
        return "Less than 1 min"
    days = time_val // 86400
    hours = (time_val % 86400) // 3600
    minutes = (time_val % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}hr")
    if minutes > 0:
        parts.append(f"{minutes}min")
    return " ".join(parts)


DERIVED_SENSORS: list[dict[str, Any]] = [
    # --- WAN-derived sensors ---
    {
        "name": "UDM CPU",
        "key": "wan_cpu",
        "source": SENSOR_WAN,
        "unit": "%",
        "icon": None,
        "value_fn": lambda a: (a.get("gw_system-stats") or {}).get("cpu", 0),
    },
    {
        "name": "UDM Memory",
        "key": "wan_mem",
        "source": SENSOR_WAN,
        "unit": "%",
        "icon": None,
        "value_fn": lambda a: (a.get("gw_system-stats") or {}).get("mem", 0),
    },
    {
        "name": "WAN IP",
        "key": "wan_ip",
        "source": SENSOR_WAN,
        "unit": None,
        "icon": None,
        "value_fn": lambda a: a.get("wan_ip"),
    },
    {
        "name": "WAN Download",
        "key": "wan_download",
        "source": SENSOR_WAN,
        "unit": "Kbps",
        "icon": "mdi:progress-download",
        "value_fn": lambda a: int((a.get("rx_bytes-r") or 0) / 1024),
    },
    {
        "name": "WAN Upload",
        "key": "wan_upload",
        "source": SENSOR_WAN,
        "unit": "Kbps",
        "icon": "mdi:progress-upload",
        "value_fn": lambda a: int((a.get("tx_bytes-r") or 0) / 1024),
    },
    {
        "name": "UDM Uptime",
        "key": "wan_uptime",
        "source": SENSOR_WAN,
        "unit": None,
        "icon": None,
        "value_fn": lambda a: _format_uptime(
            (a.get("gw_system-stats") or {}).get("uptime", 0)
        ),
    },
    {
        "name": "UDM Firmware Version",
        "key": "firmware_version",
        "source": SENSOR_WAN,
        "unit": None,
        "icon": "mdi:database-plus",
        "value_fn": lambda a: a.get("gw_version"),
    },
    # --- WWW-derived sensors ---
    {
        "name": "UDM Speedtest Download",
        "key": "www_xput_down",
        "source": SENSOR_WWW,
        "unit": "Mbps",
        "icon": "mdi:progress-download",
        "value_fn": lambda a: a.get("xput_down"),
    },
    {
        "name": "UDM Speedtest Upload",
        "key": "www_xput_up",
        "source": SENSOR_WWW,
        "unit": "Mbps",
        "icon": "mdi:progress-upload",
        "value_fn": lambda a: a.get("xput_up"),
    },
    {
        "name": "UDM Speedtest Ping",
        "key": "www_speedtest_ping",
        "source": SENSOR_WWW,
        "unit": "ms",
        "icon": "mdi:progress-clock",
        "value_fn": lambda a: a.get("speedtest_ping"),
    },
    {
        "name": "Internet Uptime",
        "key": "www_uptime",
        "source": SENSOR_WWW,
        "unit": None,
        "icon": None,
        "value_fn": lambda a: _format_uptime(a.get("uptime", 0)),
    },
    # --- WLAN-derived sensor ---
    {
        "name": "Users Wifi",
        "key": "wlan_num_user",
        "source": SENSOR_WLAN,
        "unit": None,
        "icon": "mdi:account-multiple",
        "value_fn": lambda a: a.get("num_user"),
    },
    # --- LAN-derived sensor ---
    {
        "name": "Users Lan",
        "key": "lan_num_user",
        "source": SENSOR_LAN,
        "unit": None,
        "icon": "mdi:account-multiple",
        "value_fn": lambda a: a.get("num_user"),
    },
    # --- Alerts-derived sensor ---
    {
        "name": "Last Alert",
        "key": "last_alert",
        "source": SENSOR_ALERTS,
        "unit": None,
        "icon": "mdi:alert-outline",
        "value_fn": lambda a: (a.get("1") or {}).get("msg", "Aucune alerte"),
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Status sensors from a config entry."""
    coordinator: UnifiStatusCoordinator = hass.data[DOMAIN][entry.entry_id]

    monitored = entry.options.get(CONF_MONITORED_CONDITIONS, DEFAULT_MONITORED)

    entities: list[SensorEntity] = []

    for sensor_type in monitored:
        entities.append(UnifiStatusSensor(coordinator, entry, sensor_type))

    for derived_cfg in DERIVED_SENSORS:
        if derived_cfg["source"] in monitored:
            entities.append(UnifiDerivedSensor(coordinator, entry, derived_cfg))

    async_add_entities(entities)


class UnifiStatusSensor(CoordinatorEntity[UnifiStatusCoordinator], SensorEntity):
    """A base UniFi subsystem status sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiStatusCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = USG_SENSORS[sensor_type][0]
        self._attr_icon = USG_SENSORS[sensor_type][2]
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the controller."""
        host = self.coordinator.config_entry.data.get("host", "unknown")
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=f"UniFi Controller ({host})",
            manufacturer="Ubiquiti",
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        data = self.coordinator.data
        if data is None:
            return None

        if self._sensor_type == SENSOR_ALERTS:
            alerts = data.get("alerts", [])
            count = sum(1 for a in alerts if not a.get("archived"))
            return count

        if self._sensor_type == SENSOR_FIRMWARE:
            aps = data.get("aps", [])
            count = sum(1 for d in aps if d.get("upgradable"))
            return count

        for sub in data.get("healthinfo", []):
            if sub.get("subsystem") == self._sensor_type:
                return sub.get("status", "").upper()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes."""
        data = self.coordinator.data
        if data is None:
            return {}

        if self._sensor_type == SENSOR_ALERTS:
            attrs = {}
            for i, alert in enumerate(data.get("alerts", []), start=1):
                if not alert.get("archived"):
                    attrs[str(i)] = alert
            return attrs

        if self._sensor_type == SENSOR_FIRMWARE:
            attrs = {}
            for device in data.get("aps", []):
                if device.get("upgradable"):
                    key = device.get("name") or device.get("ip", "unknown")
                    attrs[key] = device["upgradable"]
            return attrs

        for sub in data.get("healthinfo", []):
            if sub.get("subsystem") == self._sensor_type:
                return dict(sub)

        return {}


class UnifiDerivedSensor(CoordinatorEntity[UnifiStatusCoordinator], SensorEntity):
    """A derived sensor that extracts a specific value from base sensor data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiStatusCoordinator,
        entry: ConfigEntry,
        config: dict[str, Any],
    ) -> None:
        """Initialize the derived sensor."""
        super().__init__(coordinator)
        self._source = config["source"]
        self._value_fn = config["value_fn"]
        self._attr_name = config["name"]
        self._attr_unique_id = f"{entry.entry_id}_{config['key']}"
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_icon = config.get("icon")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the controller."""
        host = self.coordinator.config_entry.data.get("host", "unknown")
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=f"UniFi Controller ({host})",
            manufacturer="Ubiquiti",
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        attrs = self._get_source_attributes()
        if attrs is None:
            return None
        try:
            return self._value_fn(attrs)
        except (KeyError, TypeError, ValueError):
            return None

    def _get_source_attributes(self) -> dict[str, Any] | None:
        """Get the source data dict for this derived sensor."""
        data = self.coordinator.data
        if data is None:
            return None

        if self._source == SENSOR_ALERTS:
            alerts = data.get("alerts", [])
            attrs: dict[str, Any] = {}
            for i, alert in enumerate(alerts, start=1):
                if not alert.get("archived"):
                    attrs[str(i)] = alert
            return attrs

        for sub in data.get("healthinfo", []):
            if sub.get("subsystem") == self._source:
                return sub

        return None
