"""
Weighbridge site profile for Mines-WB.

checkpoint-config stores ``weighbridge`` (older files may say tare_wb,
vadaghat_wb, or gross_wb). Trip behavior still follows the first field of
``truck_details`` (T / V / G). API paths are the common ones in iot_configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_WEIGHBRIDGE_ALIASES = {
    "tare",
    "tare_wb",
    "tare-wb",
    "vadaghat",
    "vadaghat_wb",
    "vadghat_wb",
    "vadhghat_wb",
    "gross",
    "gross_wb",
    "gross-wb",
    "weighbridge",
}


@dataclass(frozen=True)
class WbBrand:
    checkpoint_type: str
    label: str
    logo: str
    service_name: str


_COMMON = WbBrand(
    checkpoint_type="weighbridge",
    label="Weigh Bridge",
    logo="WB",
    service_name="GMDC Mines WB",
)


def normalize_checkpoint_type(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower().replace(" ", "_")
    if not key or key in _WEIGHBRIDGE_ALIASES:
        return "weighbridge"
    return "weighbridge"


def get_brand(checkpoint_type: Optional[str]) -> WbBrand:
    normalize_checkpoint_type(checkpoint_type)
    return _COMMON
