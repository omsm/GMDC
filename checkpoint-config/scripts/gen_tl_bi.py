#!/usr/bin/env python3
"""Generate bidirectional traffic light partial HTML."""
from pathlib import Path

dirs = [
    ("entry_a", "directionA", "ENTRY A", "arrow-right-circle", [(0, 1, "entry"), (2, 3, "exit")]),
    ("entry_b", "directionB", "ENTRY B", "arrow-left-circle", [(4, 5, "entry"), (6, 7, "exit")]),
]
lines = ['<motion id="tlBidirectionalBlock" style="display: none;">']
for dk, prefix, label, icon, sides in dirs:
    lines.append(f'    <p class="direction-subsection-title"><i class="bi bi-{icon}"></i> {label}</p>')
    lines.append('    <div class="tl-config-grid">')
    for rpin, gpin, side in sides:
        side_label = side.capitalize()
        lines.append(f'''        <div class="device-config-card">
            <div class="device-header">
                <span class="device-name">{label} - {side_label} Traffic Light</span>
                <span class="device-status" id="{prefix}_{side}TLStatus"></span>
            </div>
            <div class="device-fields">
                <div class="row">
                    <motion class="col-md-6"><motion class="form-group"><label>Make / Brand</label><input type="text" class="form-control" id="{prefix}_{side}TLMake"></div></div>
                    <div class="col-md-6"><div class="form-group"><label>Model Number</label><input type="text" class="form-control" id="{prefix}_{side}TLModel"></div></div>
                </div>
                <div class="row">
                    <div class="col-md-6"><div class="form-group"><label>Red Pin</label><input type="number" class="form-control" id="{prefix}_{side}RedPin" value="{rpin}" min="0"></div></div>
                    <div class="col-md-6"><div class="form-group"><label>Green Pin</label><input type="number" class="form-control" id="{prefix}_{side}GreenPin" value="{gpin}" min="0"></div></div>
                </div>
            </div>
            <div class="btn-group-actions" style="margin-top: 12px;">
                <button class="btn btn-sm btn-error" onclick="testTrafficLightColor('{dk}', '{side}', 'red')"><i class="bi bi-circle-fill"></i> Test Red</button>
                <button class="btn btn-sm btn-success" onclick="testTrafficLightColor('{dk}', '{side}', 'green')"><i class="bi bi-circle-fill"></i> Test Green</button>
                <button type="button" class="btn btn-sm btn-outline skip-btn skip-tl-debug" onclick="skipTrafficLightTest('{side}', '{dk}')"><i class="bi bi-skip-forward"></i> Skip</button>
            </div>
        </div>''')
    lines.append("    </div>")
lines.append("</div>")
content = "\n".join(lines).replace("motion", "div")
out = Path(__file__).resolve().parents[1] / "templates" / "partials" / "tl_bidirectional_direct.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(content, encoding="utf-8")
print("Wrote", out)
