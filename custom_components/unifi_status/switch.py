"""
Support for Unifi Status Units
"""

from __future__ import annotations

import logging
from pprint import pformat, pprint

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
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
    }
)


class UnifiSwitchData:
    """Centralizes the get_aps() API call for all UniFi switches."""

    def __init__(self, ctrl):
        """Initialize the shared data object."""
        self._ctrl = ctrl
        self.aps = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch device data from the controller."""
        from .pyunifi.controller import APIError

        try:
            self.aps = self._ctrl.get_aps()
            _LOGGER.debug(f"switch get_aps:\n{pformat(self.aps)}")
        except APIError as ex:
            _LOGGER.error(f"Update | Failed to scan aps: {ex}")
            self.aps = None


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Unifi switch."""
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
        _LOGGER.error(f"Setup | Failed to connect to Unifi Conroler: {ex}")
        return False

    switch_data = UnifiSwitchData(ctrl)

    try:
        aps = ctrl.get_aps()
    except APIError as ex:
        _LOGGER.error(f"Setup | Failed to scan aps: {ex}")
        return False

    switches = []
    for device in aps:
        if device.get("name"):
            switch = device["name"]
        else:
            switch = device["ip"]
        switches.append(
            UnifiStatusSwitch(
                hass,
                ctrl,
                switch_data,
                f"{name} {switch} Restart",
                [device["device_id"], 0],
            )
        )
        if device.get("port_table"):
            for port in device["port_table"]:
                if port.get("port_poe") == True:
                    _LOGGER.debug(f"Setup | !!! {switch} {port['name']}")
                    switches.append(
                        UnifiStatusSwitch(
                            hass,
                            ctrl,
                            switch_data,
                            f"{name} {switch} PoE {port['name']}",
                            [device["device_id"], port["port_idx"]],
                        )
                    )
    add_entities(switches, True)


class UnifiStatusSwitch(SwitchEntity):
    """Implementation of a UniFi Status switch."""

    def __init__(self, hass, ctrl, switch_data, name, switch_id):
        """Initialize the switch."""
        self._hass = hass
        self._ctrl = ctrl
        self._switch_data = switch_data
        self._name = name
        self._dev_id = switch_id[0]
        self._port_id = switch_id[1]
        self._mac = None
        self._state = STATE_UNKNOWN
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def available(self):
        """Return the availability of this switch."""
        _LOGGER.debug(f"[{self._name}] State: {self._state}")
        return self._state is not None

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    def turn_on(self, **kwargs):
        """Turn the device on."""
        if self._port_id == 0:
            self._ctrl.restart_ap(self._mac)
            self._state = STATE_ON
        elif self._port_id != 0:
            _LOGGER.debug(f"port on: {self._mac} {self._port_id} {type(self._port_id)}")
            self._ctrl.switch_port_power_on(self._mac, self._port_id)
            self._state = STATE_ON

    def turn_off(self, **kwargs):
        """Turn the device off."""
        if self._port_id == 0:
            self._state = STATE_OFF
        elif self._port_id != 0:
            _LOGGER.debug(
                f"port off : {self._mac} {self._port_id} {type(self._port_id)}"
            )
            self._ctrl.switch_port_power_off(self._mac, self._port_id)
            self._state = STATE_OFF

    @property
    def state_attributes(self):
        """Return the device state attributes."""
        return self._attributes

    def update(self):
        """Set up the switch."""
        self._switch_data.update()

        if self._switch_data.aps is None:
            self._state = STATE_UNAVAILABLE
            return

        for device in self._switch_data.aps:
            if self._dev_id == device["device_id"] and self._port_id == 0:
                self._mac = device["mac"]
                self._attributes["model"] = device["model"]
                self._attributes["serial"] = device["serial"]
                self._attributes["version"] = device["version"]
                self._attributes["ip"] = device["ip"]
                self._attributes["mac"] = device["mac"]

                if device.get("uptime"):
                    self._attributes["uptime"] = device["uptime"]

                if device["state"] in [1, 4, 5, 6]:
                    self._state = STATE_OFF
                else:
                    _LOGGER.debug(
                        f"Update | set state unavail {self._dev_id} {self._port_id}"
                    )
                    self._state = STATE_UNAVAILABLE

            elif self._dev_id == device["device_id"] and self._port_id != 0:
                self._attributes = {}
                _LOGGER.debug(f"port index : {self._port_id} {type(self._port_id)}")
                if device["state"] in [1, 4, 5, 6]:
                    try:
                        for port in device["port_table"]:
                            if port["port_idx"] == self._port_id:
                                self._mac = device["mac"]
                                if port["poe_mode"] == "auto":
                                    self._state = STATE_ON
                                    self._attributes["poe_voltage"] = port[
                                        "poe_voltage"
                                    ]
                                    self._attributes["poe_current"] = port[
                                        "poe_current"
                                    ]
                                    self._attributes["poe_power"] = port["poe_power"]
                                else:
                                    self._state = STATE_OFF
                    except Exception as ex:
                        self._state = STATE_UNAVAILABLE
                        _LOGGER.error(f"Update | Failed detect port status: {ex}")
                else:
                    _LOGGER.debug(
                        f"Update | set state unavail did {self._dev_id} pid {self._port_id} state {device['state']}"
                    )
                    self._state = STATE_UNAVAILABLE

        _LOGGER.debug(f"end of update {self._dev_id} {self._port_id}")


"""
api state value:
0 = disconnected
1 = connected
4 = upgrading
5 = provisioning
6 = heartbeat missed
7 = adopting
"""
