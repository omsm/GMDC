"""
Weighbridge site profiles for Mines-WB.

One runtime serves tare_wb, vadaghat_wb, and gross_wb. Trip behavior still
follows truck_details T| / V| / G| prefixes from OCI; checkpoint_type drives
dashboard labels and which sample config / API paths are expected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


_ALIASES = {
    "tare": "tare_wb",
    "tare-wb": "tare_wb",
    "vadghat_wb": "vadaghat_wb",  # legacy spelling in older JSON
    "vadhghat_wb": "vadaghat_wb",
    "vadaghat": "vadaghat_wb",
    "gross": "gross_wb",
    "gross-wb": "gross_wb",
}


@dataclass(frozen=True)
class WbBrand:
    checkpoint_type: str
    label: str
    logo: str
    service_name: str


_BRANDS: Dict[str, WbBrand] = {
    "tare_wb": WbBrand(
        checkpoint_type="tare_wb",
        label="Tare Weighbridge",
        logo="TW",
        service_name="GMDC Mines WB",
    ),
    "vadaghat_wb": WbBrand(
        checkpoint_type="vadaghat_wb",
        label="Vadaghat Weighbridge",
        logo="VW",
        service_name="GMDC Mines WB",
    ),
    "gross_wb": WbBrand(
        checkpoint_type="gross_wb",
        label="Gross Weighbridge",
        logo="GW",
        service_name="GMDC Mines WB",
    ),
}


def normalize_checkpoint_type(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower().replace(" ", "_")
    if not key:
        return "tare_wb"
    key = _ALIASES.get(key, key)
    if key in _BRANDS:
        return key
    return "tare_wb"


def get_brand(checkpoint_type: Optional[str]) -> WbBrand:
    return _BRANDS[normalize_checkpoint_type(checkpoint_type)]
