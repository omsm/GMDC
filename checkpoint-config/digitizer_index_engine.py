"""
digitizer_index_engine.py — shared index-based digitizer weight extraction engine.

This module is copied **verbatim** into both IoT-Configuration and Weighbridge-App.
Every digitizer format is handled here through operator-picked byte indices — there
are NO per-site code paths.

Canonical extraction behavior matches ``digitizer-demo/digitizer-demo-test.py``
(run ``python digitizer-demo/digitizer-demo-test.py --simulation --self-test`` →
25/25 must pass). See ``digitizer-demo/FUTURE_INDEX_PICKER_UI_SPEC.md`` (release 2.3.4).

Public surface
--------------
- ``IndexConfig``                 extraction rules (dataclass)
- ``extract_weight(raw, cfg)``    the engine
- ``config_from_indexing(d)``     build IndexConfig from an ``indexing`` JSON block
- ``extract_weight_from_indexing(raw, d)``
- ``validate_pick_indices(picks, sample_len)``
- ``validate_indexing_for_calibration(indexing)``
- ``build_indexing_from_picks(picks, sample)``
- ``picks_from_indexing(sample, indexing)``
- ``encode_frame_bytes`` / ``decode_frame_field``  (JSON-safe escape round-trip)
- ``build_ruler(raw)``            ruler payload for the picker UI
- ``ROW_LABELS``, ``WIZARD_CAPTURE_BYTES``, ``DIGITIZER_INDEX_MIN_SAVE_WEIGHT_KG``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Number of bytes captured from the digitizer for the index picker.
WIZARD_CAPTURE_BYTES = 45

# Minimum live/preview weight (kg) required before a calibration can be saved.
DIGITIZER_INDEX_MIN_SAVE_WEIGHT_KG = 50

# Default sanity ceiling — accept heavy mining gross weights (e.g. 231050 kg).
DEFAULT_MAX_WEIGHT_KG = 999_999.0

# Only rescale obvious extra-digit overflow errors (e.g. 2500000 -> 250000),
# never legitimate 6-digit weights like 231050.
DIVIDE_BY_10_THRESHOLD_KG = 1_000_000.0

# Six technical labels for the picker rows (rows 1, 3, and 4 are required).
ROW_LABELS = [
    "Starting Raw String index 1   (frame-start char a)",
    "Starting Raw String index 2   (frame-start char b, optional)",
    "Starting Raw Weight Data idx  (first weight byte)",
    "Ending Raw Weight Data idx    (LAST weight byte, INCLUSIVE)",
    "Ending Raw String index 1     (frame-end char a, optional)",
    "Ending Raw String index 2     (frame-end char b, optional)",
]


# ---------------------------------------------------------------------------
# Whitespace helpers (dynamic — apply to all digitizers)
# ---------------------------------------------------------------------------

_DIGIT_RUN_RE = re.compile(rb"[+-]?\d+(?:\.\d+)?")

# Insignificant whitespace bytes: space, tab, CR, LF.
_WHITESPACE_BYTES = frozenset((0x20, 0x09, 0x0D, 0x0A))


def _is_whitespace(byte_val: int) -> bool:
    return byte_val in _WHITESPACE_BYTES


def _strip_whitespace(data: bytes) -> bytes:
    if not data:
        return data
    return bytes(b for b in data if not _is_whitespace(b))


def _locate_bytes_after_weight(
    raw: bytes, start: int, needle: bytes
) -> Optional[int]:
    """
    Validate ``needle`` (frame-end marker) immediately after the weight slice.

    - empty needle             → valid at ``start``
    - needle is all whitespace → must match at ``start`` exactly (do not skip)
    - needle is non-whitespace → skip any whitespace run, then require match
    - other byte before needle → reject (None)
    """
    if not needle:
        return start
    if start < 0 or start >= len(raw):
        return None
    if all(_is_whitespace(b) for b in needle):
        if start + len(needle) <= len(raw) and raw[start : start + len(needle)] == needle:
            return start
        return None
    pos = start
    while pos < len(raw) and _is_whitespace(raw[pos]):
        pos += 1
    if pos + len(needle) > len(raw):
        return None
    if raw[pos : pos + len(needle)] == needle:
        return pos
    return None


def _digits_from_weight_field(
    field_bytes: bytes,
    integer_start: Optional[int],
    integer_end: Optional[int],
) -> Optional[bytes]:
    if 0x00 in field_bytes:
        return None
    if integer_start is not None and integer_end is not None:
        sub = field_bytes[max(0, integer_start) : min(len(field_bytes), integer_end)]
    else:
        sub = field_bytes
    if 0x00 in sub:
        return None
    collapsed = _strip_whitespace(sub)
    if not collapsed:
        return None
    if all(0x30 <= b <= 0x39 for b in collapsed):
        return collapsed
    match = _DIGIT_RUN_RE.search(collapsed)
    return match.group(0) if match else None


def _weight_field_is_digits_and_spaces(field_bytes: bytes) -> bool:
    """True when the weight slice contains only ASCII spaces and digits."""
    if not field_bytes:
        return False
    has_digit = False
    for b in field_bytes:
        if b == 0x20:
            continue
        if 0x30 <= b <= 0x39:
            has_digit = True
            continue
        return False
    return has_digit


def _is_stx_index_frame_valid(raw: bytes, cfg: IndexConfig) -> bool:
    """
    Strict validation for ``<STX> <weight><ETX><CR><LF>`` indicators.

    Rejects merged/partial serial garbage that still contains STX/ETX markers
    (e.g. null bytes inside the weight field or frames without CRLF).
    """
    anchor = cfg.anchor_offset(raw)
    if anchor is None:
        return False

    frame_len = cfg.weight_end + 3  # ETX + CR + LF
    if len(raw) - anchor != frame_len:
        return False

    etx_pos = anchor + cfg.weight_end
    if etx_pos >= len(raw) or raw[etx_pos] != 0x03:
        return False
    if raw[etx_pos + 1 : etx_pos + 3] != b"\r\n":
        return False

    if cfg.weight_start >= 2 and anchor + 1 < len(raw):
        if raw[anchor + 1] != 0x20:
            return False

    s, e = anchor + cfg.weight_start, anchor + cfg.weight_end
    if s < 0 or e <= s or e > len(raw):
        return False
    return _weight_field_is_digits_and_spaces(raw[s:e])


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


@dataclass
class IndexConfig:
    """
    Site-specific extraction rules.

    Two addressing modes:

    1. **Absolute** (default): ``weight_start`` / ``weight_end`` are byte
       offsets directly into the raw buffer.

    2. **Anchored** (when ``frame_start_char`` is set): indices become offsets
       relative to the first occurrence of ``frame_start_char`` in the buffer.
    """

    weight_start: int
    weight_end: int
    integer_start: Optional[int] = None
    integer_end: Optional[int] = None
    decimals: int = 0
    scale: float = 1.0
    min_kg: float = 0.0
    max_kg: float = 999_999.0
    divide_by_10_above_max: bool = True
    frame_start_char: Optional[bytes] = None
    frame_end_char: Optional[bytes] = None

    def slice_keys(self) -> Tuple[int, int]:
        return self.weight_start, self.weight_end

    def anchor_offset(self, raw: bytes) -> Optional[int]:
        if not self.frame_start_char:
            return 0
        pos = raw.find(self.frame_start_char)
        return pos if pos >= 0 else None

    def resolve_slice(self, raw: bytes) -> Optional[Tuple[int, int]]:
        anchor = self.anchor_offset(raw)
        if anchor is None:
            return None
        return anchor + self.weight_start, anchor + self.weight_end


# ---------------------------------------------------------------------------
# Extraction engine
# ---------------------------------------------------------------------------


def extract_weight(raw: bytes, cfg: IndexConfig) -> Optional[float]:
    """
    Pull the weight from a raw byte buffer using configured indices.

    Returns ``None`` if the buffer is too short, the anchor is missing, or
    the digit parse fails. Never raises on bad input.
    """
    if not raw:
        return None

    resolved = cfg.resolve_slice(raw)
    if resolved is None:
        return None
    s, e = resolved
    if s < 0 or e <= s or s >= len(raw):
        return None
    e = min(e, len(raw))

    field_bytes = raw[s:e]

    if cfg.frame_start_char == b"\x02" and not _is_stx_index_frame_valid(raw, cfg):
        return None

    if cfg.frame_end_char and _locate_bytes_after_weight(raw, e, cfg.frame_end_char) is None:
        return None

    digits_bytes = _digits_from_weight_field(
        field_bytes, cfg.integer_start, cfg.integer_end
    )
    if not digits_bytes:
        return None

    try:
        digits_text = digits_bytes.decode("ascii", errors="ignore").strip()
    except Exception:
        return None
    if not digits_text:
        return None

    try:
        value = float(digits_text)
    except ValueError:
        return None

    if cfg.decimals > 0:
        value = value / (10 ** cfg.decimals)
    value *= cfg.scale

    return _apply_sanity(value, cfg)


def _apply_sanity(value: float, cfg: IndexConfig) -> Optional[float]:
    # Reject below the floor.
    if value < cfg.min_kg:
        return None
    # Accept anything up to the ceiling as-is (231050 stays 231050).
    if value <= cfg.max_kg:
        return value
    # Above the ceiling: only rescale clear extra-digit overflow (>= 1,000,000),
    # so a real 6-digit weight is never silently divided by 10.
    if cfg.divide_by_10_above_max and value >= DIVIDE_BY_10_THRESHOLD_KG:
        scaled = int(value) / 10
        if scaled >= cfg.min_kg:
            return scaled
    return None


# ---------------------------------------------------------------------------
# JSON-safe escape round-trip for frame bytes
# ---------------------------------------------------------------------------

_HEX_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{2})")


def encode_frame_bytes(value: Optional[bytes]) -> Optional[str]:
    """Encode frame bytes to a JSON-safe string (printable as-is, else \\xHH)."""
    if value is None:
        return None
    out: List[str] = []
    for byte in value:
        if byte == 0x0D:
            out.append("\\r")
        elif byte == 0x0A:
            out.append("\\n")
        elif byte == 0x09:
            out.append("\\t")
        elif 0x20 <= byte < 0x7F:
            out.append(chr(byte))
        else:
            out.append(f"\\x{byte:02x}")
    return "".join(out)


def decode_frame_field(value: Any) -> Optional[bytes]:
    """Decode a stored frame string (with \\xHH / \\r / \\n / \\t) back to bytes."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value) or None
    text = str(value)
    if not text:
        return None
    text = text.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")
    text = _HEX_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    decoded = text.encode("latin-1", errors="ignore")
    return decoded or None


# ---------------------------------------------------------------------------
# indexing JSON <-> IndexConfig
# ---------------------------------------------------------------------------


def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def config_from_indexing(indexing: Optional[Dict[str, Any]]) -> Optional[IndexConfig]:
    """Build an :class:`IndexConfig` from a stored ``indexing`` JSON block."""
    if not indexing:
        return None
    weight_start = _opt_int(indexing.get("weight_start"))
    weight_end = _opt_int(indexing.get("weight_end"))
    if weight_start is None or weight_end is None:
        return None
    try:
        decimals = int(indexing.get("decimals", 0) or 0)
    except (TypeError, ValueError):
        decimals = 0
    try:
        scale = float(indexing.get("scale", 1.0) or 1.0)
    except (TypeError, ValueError):
        scale = 1.0
    return IndexConfig(
        weight_start=weight_start,
        weight_end=weight_end,
        integer_start=_opt_int(indexing.get("integer_start")),
        integer_end=_opt_int(indexing.get("integer_end")),
        decimals=decimals,
        scale=scale,
        frame_start_char=decode_frame_field(indexing.get("frame_start_char")),
        frame_end_char=decode_frame_field(indexing.get("frame_end_char")),
    )


def extract_weight_from_indexing(
    raw: bytes, indexing: Optional[Dict[str, Any]]
) -> Optional[float]:
    """Convenience: build a config from ``indexing`` and extract in one call."""
    cfg = config_from_indexing(indexing)
    if cfg is None:
        return None
    return extract_weight(raw, cfg)


def _frame_end_exclusive(raw: bytes, anchor: int, cfg: IndexConfig) -> Optional[int]:
    """Return exclusive end offset of one frame starting at ``anchor``."""
    if cfg.frame_end_char:
        loc = raw.find(cfg.frame_end_char, anchor)
        if loc < 0:
            return None
        return loc + len(cfg.frame_end_char)
    if cfg.frame_start_char == b"\x02":
        etx = raw.find(b"\x03", anchor)
        if etx < 0:
            return None
        end = etx + 1
        if end < len(raw) and raw[end : end + 1] == b"\r":
            end += 1
        if end < len(raw) and raw[end : end + 1] == b"\n":
            end += 1
        return end
    return len(raw)


def is_index_frame_complete(raw: bytes, indexing: Optional[Dict[str, Any]]) -> bool:
    """
    Return True when configured frame start/end markers are present and the
    weight slice fits inside the buffer.
    """
    if not raw or not indexing:
        return False
    cfg = config_from_indexing(indexing)
    if cfg is None:
        return False

    if cfg.frame_start_char == b"\x02":
        return _is_stx_index_frame_valid(raw, cfg)

    if cfg.frame_start_char:
        anchor = cfg.anchor_offset(raw)
        if anchor is None:
            return False
    else:
        anchor = 0

    resolved = cfg.resolve_slice(raw)
    if resolved is None:
        return False
    _s, e = resolved
    if e > len(raw):
        return False

    if cfg.frame_end_char:
        return _locate_bytes_after_weight(raw, e, cfg.frame_end_char) is not None

    return True


def extract_last_complete_index_frame(
    raw: bytes, indexing: Optional[Dict[str, Any]]
) -> Optional[bytes]:
    """From a noisy/multi-frame buffer, return the last complete indexed frame."""
    if not raw or not indexing:
        return None
    cfg = config_from_indexing(indexing)
    if cfg is None:
        return raw if is_index_frame_complete(raw, indexing) else None

    if not cfg.frame_start_char:
        return raw if is_index_frame_complete(raw, indexing) else None

    marker = cfg.frame_start_char
    last: Optional[bytes] = None
    start = 0
    while start < len(raw):
        idx = raw.find(marker, start)
        if idx < 0:
            break
        end = _frame_end_exclusive(raw, idx, cfg)
        if end is not None and end > idx:
            candidate = raw[idx:end]
            if is_index_frame_complete(candidate, indexing):
                last = candidate
        start = idx + 1
    return last


# ---------------------------------------------------------------------------
# Pick validation + pick <-> indexing round-trip (picker UI support)
# ---------------------------------------------------------------------------


def validate_pick_indices(
    picks: List[Optional[int]], sample_len: int
) -> Optional[str]:
    """
    Validate the six picker rows. Returns an error string, or ``None`` if valid.

    Rules (see spec §8.5):
      1. Rows 1, 3, and 4 required; row 4 index >= row 3.
      2. Row 2 requires row 1; row 6 requires row 5.
      3. Monotonic indices within optional pairs.
      4. Cross-band order: frame start < weight start <= weight end < frame end.
      5. No duplicate indices across enabled rows.
      6. All indices within 0 .. sample_len-1.
    """
    if not picks or len(picks) != 6:
        return "Exactly six picker rows are required."

    for sl, idx in enumerate(picks, 1):
        if idx is None:
            continue
        if not isinstance(idx, int):
            return f"Row {sl} index must be a whole number."
        if idx < 0 or idx >= sample_len:
            return f"Row {sl} index {idx} is out of range (0..{sample_len - 1})."

    i1, i2, i3, i4, i5, i6 = picks

    if i1 is None:
        return "Row 1 (start of weight message — 1st character) is required."
    if i3 is None or i4 is None:
        return "Rows 3 and 4 (weight start and end) are required."
    if i4 < i3:
        return f"Row 4 (index {i4}) must be greater than or equal to Row 3 (index {i3})."
    if i2 is not None and i1 is None:
        return "Row 2 is set without Row 1. Enable Row 1 or clear Row 2."
    if i1 is not None and i2 is not None and i2 < i1:
        return f"Row 2 (index {i2}) must be greater than or equal to Row 1 (index {i1})."
    if i6 is not None and i5 is None:
        return "Row 6 is set without Row 5. Enable Row 5 or clear Row 6."
    if i5 is not None and i6 is not None and i6 < i5:
        return f"Row 6 (index {i6}) must be greater than or equal to Row 5 (index {i5})."

    # Cross-band ordering: positions must progress left-to-right on the serial stream.
    frame_start_last = i2 if i2 is not None else i1
    if i3 is not None and frame_start_last is not None and i3 <= frame_start_last:
        return (
            f"Row 3 (weight start, index {i3}) must be after frame start "
            f"(row {2 if i2 is not None else 1}, index {frame_start_last})."
        )
    if i5 is not None and i4 is not None and i5 <= i4:
        return (
            f"Row 5 (frame end 1st char, index {i5}) must be after the last weight "
            f"digit (row 4, index {i4})."
        )

    seen: Dict[int, int] = {}
    for sl, idx in enumerate(picks, 1):
        if idx is None:
            continue
        if idx in seen:
            return f"Rows {seen[idx]} and {sl} cannot use the same position ({idx})."
        seen[idx] = sl

    return None


def validate_indexing_for_calibration(indexing: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Validate a saved ``indexing`` block before digitizer calibration is stored.

    Row 1 (frame start) is mandatory — same as weight start/end rows in the picker.
    """
    if not indexing or not isinstance(indexing, dict):
        return "Indexing configuration is required."
    weight_start = _opt_int(indexing.get("weight_start"))
    weight_end = _opt_int(indexing.get("weight_end"))
    if weight_start is None or weight_end is None:
        return "Weight start and end indices are required in indexing."
    if weight_end <= weight_start:
        return (
            f"Weight end offset ({weight_end}) must be greater than "
            f"weight start offset ({weight_start})."
        )
    frame_start = decode_frame_field(indexing.get("frame_start_char"))
    if not frame_start:
        return (
            "Start of weight message — 1st character (row 1) is required, "
            "same as the weight number rows."
        )
    return None


def build_indexing_from_picks(
    picks: List[Optional[int]], sample: bytes
) -> Dict[str, Any]:
    """
    Translate six picker rows into an ``indexing`` JSON block (spec §7).

    Row 4 is INCLUSIVE in the picker; engine ``weight_end`` is EXCLUSIVE, so we
    store ``(i4 + 1) - anchor``. Row 1 (frame start) is required; weight indices
    are stored as OFFSETS from the frame-start anchor.
    """
    err = validate_pick_indices(picks, len(sample))
    if err:
        raise ValueError(err)

    i1, i2, i3, i4, i5, i6 = picks
    anchor = i1 if i1 is not None else 0

    frame_start: Optional[bytes] = None
    if i1 is not None:
        end = (i2 if i2 is not None else i1) + 1
        frame_start = bytes(sample[i1:end])

    frame_end: Optional[bytes] = None
    if i5 is not None:
        end = (i6 if i6 is not None else i5) + 1
        frame_end = bytes(sample[i5:end])

    return {
        "frame_start_char": encode_frame_bytes(frame_start),
        "frame_end_char": encode_frame_bytes(frame_end),
        "weight_start": i3 - anchor,
        "weight_end": (i4 + 1) - anchor,
        "integer_start": None,
        "integer_end": None,
        "decimals": 0,
        "scale": 1.0,
    }


def picks_from_indexing(
    sample: bytes, indexing: Optional[Dict[str, Any]]
) -> List[Optional[int]]:
    """
    Inverse of :func:`build_indexing_from_picks` — restore the six picker rows
    for a given sample so the modal can re-open with the operator's choices.

    Uses :func:`_locate_bytes_after_weight` for the frame-end rows, so a frame-end
    marker after a whitespace gap (e.g. ``A`` at index 27 with a space at 26) is
    restored to the marker index, not the whitespace.
    """
    picks: List[Optional[int]] = [None, None, None, None, None, None]
    if not indexing:
        return picks

    frame_start = decode_frame_field(indexing.get("frame_start_char"))
    frame_end = decode_frame_field(indexing.get("frame_end_char"))
    weight_start = _opt_int(indexing.get("weight_start"))
    weight_end = _opt_int(indexing.get("weight_end"))
    if weight_start is None or weight_end is None:
        return picks

    anchor = 0
    if frame_start:
        pos = sample.find(frame_start)
        if pos >= 0:
            anchor = pos
            picks[0] = pos
            if len(frame_start) > 1:
                picks[1] = pos + len(frame_start) - 1

    picks[2] = anchor + weight_start
    picks[3] = anchor + weight_end - 1  # exclusive end -> inclusive last byte

    if frame_end:
        weight_end_abs = anchor + weight_end
        loc = _locate_bytes_after_weight(sample, weight_end_abs, frame_end)
        if loc is not None:
            picks[4] = loc
            if len(frame_end) > 1:
                picks[5] = loc + len(frame_end) - 1

    return picks


# ---------------------------------------------------------------------------
# Ruler builder (picker UI)
# ---------------------------------------------------------------------------


def byte_display_repr(byte_val: int) -> str:
    """Printable single-byte representation for the ruler (printable, else \\xHH)."""
    if byte_val == 0x20:
        return " "
    if 0x20 < byte_val < 0x7F:
        return chr(byte_val)
    if byte_val == 0x0D:
        return "\\r"
    if byte_val == 0x0A:
        return "\\n"
    if byte_val == 0x09:
        return "\\t"
    if byte_val == 0x02:
        return "\\x02"
    if byte_val == 0x03:
        return "\\x03"
    return f"\\x{byte_val:02x}"


def build_ruler(raw: bytes) -> Dict[str, Any]:
    """
    Build the ruler payload used by the index picker modal.

    Indices are sequential (0, 1, 2 …) — not hex offsets.
    """
    n = len(raw)
    tens = "".join(str((i // 10) % 10) if i % 10 == 0 else " " for i in range(n))
    ones = "".join(str(i % 10) for i in range(n))
    ascii_chars = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in raw)
    hex_pairs = " ".join(f"{b:02x}" for b in raw)
    return {
        "length": n,
        "tens": tens,
        "ones": ones,
        "ascii": ascii_chars,
        "hex": hex_pairs,
        "bytes": [{"index": i, "repr": byte_display_repr(b)} for i, b in enumerate(raw)],
    }


# ---------------------------------------------------------------------------
# Backward-compatible aliases (conversion.py / legacy app imports)
# ---------------------------------------------------------------------------

DEFAULT_MAX_KG = DEFAULT_MAX_WEIGHT_KG
index_config_from_dict = config_from_indexing
build_ruler_payload = build_ruler


def highlight_bands(picks: List[Optional[int]]) -> Dict[str, List[int]]:
    """Return index lists per color group for UI highlighting."""
    i1, i2, i3, i4, i5, i6 = picks
    frame_start: List[int] = []
    if i1 is not None:
        end = i2 if i2 is not None else i1
        frame_start = list(range(i1, end + 1))
    weight: List[int] = []
    if i3 is not None and i4 is not None:
        weight = list(range(i3, i4 + 1))
    frame_end: List[int] = []
    if i5 is not None:
        end = i6 if i6 is not None else i5
        frame_end = list(range(i5, end + 1))
    return {
        "frame_start": frame_start,
        "weight": weight,
        "frame_end": frame_end,
    }
