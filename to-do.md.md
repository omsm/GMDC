# To-do

## Done (shipped)

### Operator Flow Details UI (v1.2+)
Simple icons for transaction steps; full step cards in a **Flow Details** modal.
Shipped on Mines-Checkpoint / Mines-WB dashboards.

---

## Pending

### Digitizer-app: API + MQTT modes (Windows & macOS)

**Scope:** `digitizer-app`, `digitizer-decoder` (new), `checkpoint-config`, `Mines-WB`

1. **Platform**
   - digitizer must run on **Windows** and **macOS**

2. **Transport mode (user selects while configuring)**
   - Dropdown: **API** | **MQTT**
   - **API** — `POST /read_stable_weight`, host/port, etc.
   - **MQTT** — broker host/port, username/password, publish + subscribe topics

3. **`digitizer-decoder/` (in progress)**
   - Web app (Flask) replacing PySide shell; same serial indexing logic as `serial_ui.py`
   - Dashboard uses Mines-Checkpoint / Mines-WB design system
   - API + MQTT mode selection with parameters — **done in decoder**
   - Original `digitizer-app/` PySide UI kept as reference

4. **checkpoint-config** — still pending
   - Digitizer section UI: mode dropdown + API / MQTT fields
   - Persist in `iot_configuration.json`

5. **Mines-WB** — still pending
   - Read digitizer mode from IoT config
   - If API → existing HTTP client
   - If MQTT → broker publish/subscribe for weight

**Status:** decoder scaffold shipped; config + Mines-WB MQTT client still open.
