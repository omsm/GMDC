"""Choose liquid glass vs the earlier UI.

OS_TYPE lives in each app entry point (app.py / main.py):
  "auto"    — macOS gets liquid glass, Windows keeps the earlier UI
  "macos"   — liquid glass, even on Windows
  "windows" — earlier UI, even on macOS
"""

from __future__ import annotations

import sys

_SCENE = """<div class="liquid-scene" aria-hidden="true">
    <div class="liquid-orb liquid-orb-a"></div>
    <div class="liquid-orb liquid-orb-b"></div>
    <div class="liquid-orb liquid-orb-c"></div>
    <div class="liquid-orb liquid-orb-d"></div>
</div>"""


def liquid_glass_enabled(os_type: str) -> bool:
    choice = str(os_type or "auto").strip().lower()
    if choice == "macos":
        return True
    if choice == "windows":
        return False
    return sys.platform == "darwin"


def inject_liquid_glass(html: str) -> str:
    """Insert the glass stylesheet and background into a static dashboard page."""
    if "liquid-glass.css" not in html:
        html = html.replace(
            "</head>",
            '<link rel="stylesheet" href="/static/css/liquid-glass.css">\n</head>',
            1,
        )
    if "liquid-scene" not in html:
        html = html.replace("<body>", "<body>\n" + _SCENE, 1)
    return html
