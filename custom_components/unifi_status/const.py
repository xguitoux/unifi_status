from __future__ import annotations

from datetime import timedelta

DOMAIN = "unifi_status"

CONF_SITE_ID = "site_id"
CONF_UNIFI_VERSION = "version"
CONF_MONITORED_CONDITIONS = "monitored_conditions"

DEFAULT_NAME = "UniFi Status"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8443
DEFAULT_UNIFI_VERSION = "v5"
DEFAULT_SITE = "default"
DEFAULT_VERIFY_SSL = False

UPDATE_INTERVAL = timedelta(seconds=30)

UNIFI_VERSIONS = ["v4", "v5", "unifiOS", "UDMP-unifiOS"]

SENSOR_VPN = "vpn"
SENSOR_WWW = "www"
SENSOR_WAN = "wan"
SENSOR_LAN = "lan"
SENSOR_WLAN = "wlan"
SENSOR_ALERTS = "alerts"
SENSOR_FIRMWARE = "firmware"

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
