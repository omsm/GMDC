# To-do

## Done (shipped)

### Operator Flow Details UI (v1.2+)
Simple icons for transaction steps; full step cards in a **Flow Details** modal.
Shipped on Mines-Checkpoint / Mines-WB dashboards.

---

## Pending

### Digitizer-app: API + MQTT modes (Windows & macOS)

**Scope:** `digitizer-app`, `checkpoint-config`, `Mines-WB`

1. **Platform**
   - digitizer-app must run on **Windows** and **macOS**

2. **Transport mode (user selects while configuring)**
   - Dropdown: **API** | **MQTT**
   - **API** — keep current parameters / behavior (`POST /read_stable_weight`, host/port, etc.)
   - **MQTT** — configure:
     - Broker host
     - Broker port
     - Username (optional)
     - Password (optional)
     - Topic to **publish**
     - Topic to **subscribe**

3. **checkpoint-config**
   - Digitizer section UI: mode dropdown + API fields or MQTT fields as above
   - Persist choice and fields in `iot_configuration.json`

4. **Mines-WB**
   - Read digitizer mode from IoT config
   - If API → existing HTTP digitizer client
   - If MQTT → connect to broker, publish/subscribe on configured topics for weight

**Status:** deferred — implement later.
