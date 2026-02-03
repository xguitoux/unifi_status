"""
Support for Unifi Status Units.
"""

from __future__ import annotations

import logging
from pprint import pformat, pprint

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_HOST,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from . import DOMAIN, PLATFORMS, __version__
from .const import (
    CONF_SITE_ID,
    CONF_UNIFI_VERSION,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SITE,
    DEFAULT_UNIFI_VERSION,
    DEFAULT_VERIFY_SSL,
    MIN_TIME_BETWEEN_UPDATES,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_VPN = "vpn"
SENSOR_WWW = "www"
SENSOR_WAN = "wan"
SENSOR_LAN = "lan"
SENSOR_WLAN = "wlan"
SENSOR_ALERTS = "alerts"
SENSOR_FIRMWARE = "firmware"

USG_SENSORS = {
    SENSOR_VPN: ["VPN", "", "mdi:folder-key-network"],
    SENSOR_WWW: ["WWW", "", "mdi:web"],
    SENSOR_WAN: ["WAN", "", "mdi:shield-outline"],
    SENSOR_LAN: ["LAN", "", "mdi:lan"],
    SENSOR_WLAN: ["WLAN", "", "mdi:wifi"],
    SENSOR_ALERTS: ["Alerts", "", "mdi:information-outline"],
    SENSOR_FIRMWARE: ["Firmware Upgradable", "", "mdi:database-plus"],
}

POSSIBLE_MONITORED = [
    SENSOR_VPN,
    SENSOR_WWW,
    SENSOR_WAN,
    SENSOR_LAN,
    SENSOR_WLAN,
    SENSOR_ALERTS,
    SENSOR_FIRMWARE,
]
DEFAULT_MONITORED = POSSIBLE_MONITORED

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
        vol.Optional(CONF_SITE_ID, default=DEFAULT_SITE): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_UNIFI_VERSION, default=DEFAULT_UNIFI_VERSION): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): vol.Any(
            cv.boolean, cv.isfile
        ),
        vol.Optional(CONF_MONITORED_CONDITIONS, default=DEFAULT_MONITORED): vol.All(
            cv.ensure_list, [vol.In(POSSIBLE_MONITORED)]
        ),
    }
)


def _format_uptime(seconds):
    """Format an uptime value in seconds to a human-readable string."""
    time = int(seconds)
    if time < 60:
        return "Less than 1 min"
    days = time // 86400
    hours = (time % 86400) // 3600
    minutes = (time % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}hr")
    if minutes > 0:
        parts.append(f"{minutes}min")
    return " ".join(parts)


DERIVED_SENSORS = [
    # --- WAN-derived sensors ---
    {
        "name": "UDM CPU",
        "unique_id": "unifi_status_wan_cpu",
        "source": SENSOR_WAN,
        "unit": "%",
        "icon": None,
        "value_fn": lambda a: (a.get("gw_system-stats") or {}).get("cpu", 0),
    },
    {
        "name": "UDM Memory",
        "unique_id": "unifi_status_wan_mem",
        "source": SENSOR_WAN,
        "unit": "%",
        "icon": None,
        "value_fn": lambda a: (a.get("gw_system-stats") or {}).get("mem", 0),
    },
    {
        "name": "WAN IP",
        "unique_id": "unifi_status_wan_ip",
        "source": SENSOR_WAN,
        "unit": None,
        "icon": None,
        "value_fn": lambda a: a.get("wan_ip"),
    },
    {
        "name": "WAN Download",
        "unique_id": "unifi_status_wan_download",
        "source": SENSOR_WAN,
        "unit": "Kbps",
        "icon": "mdi:progress-download",
        "value_fn": lambda a: int((a.get("rx_bytes-r") or 0) / 1024),
    },
    {
        "name": "WAN Upload",
        "unique_id": "unifi_status_wan_upload",
        "source": SENSOR_WAN,
        "unit": "Kbps",
        "icon": "mdi:progress-upload",
        "value_fn": lambda a: int((a.get("tx_bytes-r") or 0) / 1024),
    },
    {
        "name": "UDM Uptime",
        "unique_id": "unifi_status_wan_uptime",
        "source": SENSOR_WAN,
        "unit": None,
        "icon": None,
        "value_fn": lambda a: _format_uptime(
            (a.get("gw_system-stats") or {}).get("uptime", 0)
        ),
    },
    {
        "name": "UDM Firmware Version",
        "unique_id": "unifi_status_firmware_version",
        "source": SENSOR_WAN,
        "unit": None,
        "icon": "mdi:database-plus",
        "value_fn": lambda a: a.get("gw_version"),
    },
    # --- WWW-derived sensors ---
    {
        "name": "UDM Speedtest Download",
        "unique_id": "unifi_status_www_xput_down",
        "source": SENSOR_WWW,
        "unit": "Mbps",
        "icon": "mdi:progress-download",
        "value_fn": lambda a: a.get("xput_down"),
    },
    {
        "name": "UDM Speedtest Upload",
        "unique_id": "unifi_status_www_xput_up",
        "source": SENSOR_WWW,
        "unit": "Mbps",
        "icon": "mdi:progress-upload",
        "value_fn": lambda a: a.get("xput_up"),
    },
    {
        "name": "UDM Speedtest Ping",
        "unique_id": "unifi_status_www_speedtest_ping",
        "source": SENSOR_WWW,
        "unit": "ms",
        "icon": "mdi:progress-clock",
        "value_fn": lambda a: a.get("speedtest_ping"),
    },
    {
        "name": "Internet Uptime",
        "unique_id": "unifi_status_www_uptime",
        "source": SENSOR_WWW,
        "unit": None,
        "icon": None,
        "value_fn": lambda a: _format_uptime(a.get("uptime", 0)),
    },
    # --- WLAN-derived sensor ---
    {
        "name": "Users Wifi",
        "unique_id": "unifi_status_wlan_num_user",
        "source": SENSOR_WLAN,
        "unit": None,
        "icon": "mdi:account-multiple",
        "value_fn": lambda a: a.get("num_user"),
    },
    # --- LAN-derived sensor ---
    {
        "name": "Users Lan",
        "unique_id": "unifi_status_lan_num_user",
        "source": SENSOR_LAN,
        "unit": None,
        "icon": "mdi:account-multiple",
        "value_fn": lambda a: a.get("num_user"),
    },
    # --- Alerts-derived sensor ---
    {
        "name": "Last Alert",
        "unique_id": "unifi_status_last_alert",
        "source": SENSOR_ALERTS,
        "unit": None,
        "icon": "mdi:alert-outline",
        "value_fn": lambda a: (a.get("1") or {}).get("msg", "Aucune alerte"),
    },
]


class UnifiSensorData:
    """Centralizes API calls for all UniFi sensors."""

    def __init__(self, ctrl):
        """Initialize the shared data object."""
        self._ctrl = ctrl
        self.healthinfo = None
        self.alerts = None
        self.aps = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch all data from the controller in a single cycle."""
        from .pyunifi.controller import APIError

        try:
            self.healthinfo = self._ctrl.get_healthinfo()
            _LOGGER.debug(f"get_healthinfo:\n{pformat(self.healthinfo)}")
        except APIError as ex:
            _LOGGER.error(f"Failed to access health info: {ex}")
            self.healthinfo = None

        try:
            self.alerts = self._ctrl.get_alerts()
        except APIError as ex:
            _LOGGER.error(f"Failed to access alerts info: {ex}")
            self.alerts = None

        try:
            self.aps = self._ctrl.get_aps()
            _LOGGER.debug(f"get_aps:\n{pformat(self.aps)}")
        except APIError as ex:
            _LOGGER.error(f"Failed to scan aps: {ex}")
            self.aps = None


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Unifi sensor."""
    from .pyunifi.controller import APIError, Controller

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    site_id = config.get(CONF_SITE_ID)
    version = config.get(CONF_UNIFI_VERSION)
    port = config.get(CONF_PORT)
    verify_ssl = config.get(CONF_VERIFY_SSL)

    try:
        ctrl = Controller(
            host,
            username,
            password,
            port,
            version,
            site_id=site_id,
            ssl_verify=verify_ssl,
        )
    except APIError as ex:
        _LOGGER.error(f"Failed to connect to Unifi Controler: {ex}")
        return False

    sensor_data = UnifiSensorData(ctrl)

    sensors = []
    monitored = config.get(CONF_MONITORED_CONDITIONS)
    for sensor in monitored:
        sensors.append(UnifiStatusSensor(hass, sensor_data, name, sensor))

    for derived_cfg in DERIVED_SENSORS:
        if derived_cfg["source"] in monitored:
            sensors.append(UnifiDerivedSensor(hass, sensor_data, name, derived_cfg))

    add_entities(sensors, True)


class UnifiStatusSensor(Entity):
    """Implementation of a UniFi Status sensor."""

    def __init__(self, hass, sensor_data, name, sensor):
        """Initialize the sensor."""
        self._hass = hass
        self._sensor_data = sensor_data
        self._name = name + " " + USG_SENSORS[sensor][0]
        self._sensor = sensor
        self._state = None
        self._alldata = None
        self._data = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return USG_SENSORS[self._sensor][2]

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def state_attributes(self):
        """Return the device state attributes."""
        return self._attributes

    def update(self):
        """Set up the sensor."""
        self._sensor_data.update()

        if self._sensor == SENSOR_ALERTS:
            self._attributes = {}

            if self._sensor_data.alerts is None:
                self._state = None
                return

            for index, alert in enumerate(self._sensor_data.alerts, start=1):
                if not alert["archived"]:
                    self._attributes[str(index)] = alert

            self._state = len(self._attributes)

        elif self._sensor == SENSOR_FIRMWARE:
            self._attributes = {}
            self._state = 0

            if self._sensor_data.aps is None:
                self._state = None
                return

            for devices in self._sensor_data.aps:
                if devices.get("upgradable"):
                    if devices.get("name"):
                        self._attributes[devices["name"]] = devices["upgradable"]
                    else:
                        self._attributes[devices["ip"]] = devices["upgradable"]
                    self._state += 1

        else:
            if self._sensor_data.healthinfo is None:
                self._state = None
                self._attributes = {}
                return

            self._alldata = self._sensor_data.healthinfo
            for sub in self._alldata:
                if sub["subsystem"] == self._sensor:
                    self._data = sub
                    self._state = sub["status"].upper()
                    for attr in sub:
                        self._attributes[attr] = sub[attr]


class UnifiDerivedSensor(Entity):
    """Implementation of a derived UniFi sensor that extracts a value from a base sensor's attributes."""

    def __init__(self, hass, sensor_data, name, config):
        """Initialize the derived sensor."""
        self._hass = hass
        self._sensor_data = sensor_data
        self._name = name + " " + config["name"]
        self._unique_id = config["unique_id"]
        self._source = config["source"]
        self._unit = config.get("unit")
        self._icon_str = config.get("icon")
        self._value_fn = config["value_fn"]
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return self._unique_id

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon_str

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def update(self):
        """Update the derived sensor from shared data."""
        self._sensor_data.update()
        attrs = self._get_source_attributes()
        if attrs is None:
            self._state = None
            return
        try:
            self._state = self._value_fn(attrs)
        except (KeyError, TypeError, ValueError):
            self._state = None

    def _get_source_attributes(self):
        """Retrieve the attributes dict from the source sensor's data."""
        if self._source == SENSOR_ALERTS:
            if self._sensor_data.alerts is None:
                return None
            attrs = {}
            for i, alert in enumerate(self._sensor_data.alerts, start=1):
                if not alert.get("archived"):
                    attrs[str(i)] = alert
            return attrs
        if self._sensor_data.healthinfo is None:
            return None
        for sub in self._sensor_data.healthinfo:
            if sub.get("subsystem") == self._source:
                return sub
        return None
