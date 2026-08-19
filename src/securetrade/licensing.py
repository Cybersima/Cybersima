from __future__ import annotations

from securetrade.branding import EDITION_ENTERPRISE, EDITION_PERSONAL, EDITION_PROFESSIONAL
from securetrade.models import OperatingMode


FEATURES = {
    EDITION_PERSONAL: {
        "max_venues": 2,
        "modes": {OperatingMode.LEARN, OperatingMode.ASSIST},
        "auto": False,
        "cloud_engine": False,
    },
    EDITION_PROFESSIONAL: {
        "max_venues": 8,
        "modes": {OperatingMode.LEARN, OperatingMode.ASSIST, OperatingMode.AUTO},
        "auto": True,
        "cloud_engine": True,
    },
    EDITION_ENTERPRISE: {
        "max_venues": 16,
        "modes": {OperatingMode.LEARN, OperatingMode.ASSIST, OperatingMode.AUTO},
        "auto": True,
        "cloud_engine": True,
        "admin_kill": True,
        "multi_user": True,
    },
}


def features_for(edition: str) -> dict:
    return FEATURES.get(edition, FEATURES[EDITION_PROFESSIONAL])


def mode_allowed(edition: str, mode: OperatingMode) -> bool:
    return mode in features_for(edition)["modes"]
