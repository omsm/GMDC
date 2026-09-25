# To-do

## Done (shipped)

### Operator Flow Details UI (v1.2+)
Simple icons for transaction steps; full step cards in a **Flow Details** modal.
Shipped on Mines-Checkpoint / Mines-WB dashboards.

### Digitizer MQTT + checkpoint-config (v1.8)
- Digitizer mode API|MQTT; hardcoded `gmdc/digitizer/status`; Mines-WB MQTT client + idle weight=0 + hang notify
- Server module removed from `/devices`; config reused on re-run; field edit → `validated: false`

### Flow Details icons (v1.9)
- RFID Read green on tag read; RFID Validation green on OCI success
- ANPR Update green only on `status_check` `statusCode: 201` + `vehicleStatus: 1`

---

## Pending

### Optional follow-ups
- Align PySide `digitizer-app` with decoder MQTT publish-on-change protocol
- Bidirectional ENTRY_B hardware swap
- Retire legacy `Mine-entry` / `Tracking-point-1` / `TareWb-App` when ready
