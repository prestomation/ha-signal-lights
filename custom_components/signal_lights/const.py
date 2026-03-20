"""Constants for the Signal Lights integration."""

import re

DOMAIN = "signal_lights"
PLATFORMS = ["sensor", "binary_sensor"]
STORAGE_KEY = "signal_lights"  # base key; per-entry key is signal_lights_{entry_id}
STORAGE_VERSION = 1
URL_BASE = "/signal_lights"
CARD_VERSION = "2.0.0"

# Restrict notification targets to the notify.* domain
NOTIFY_TARGET_RE = re.compile(r'^notify\.[a-z0-9_]+$')
