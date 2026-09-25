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

### Mines-WB digitizer MQTT (in progress / verify)
- **Goal:** Mines-WB digitizer path over MQTT (live weight + stable request), aligned with `digitizer-decoder`
- **Note (2026-09-26):** In the digitizer-decoder webapp, the weight is currently showing (live UI OK). Confirm Mines-WB MQTT client consumes the same topics and idle/hang behaviour end-to-end on site.
- Code already present: `Mines-WB/services/digitizer_client.py` (`DigitizerMqttClient`), config `digitizer.mode=mqtt`, topics `gmdc/digitizer/weight|request|status`
- Next: field-verify WB dashboard live weight / capture when decoder is publishing; fix gaps if any

### Optional follow-ups
- Align PySide `digitizer-app` with decoder MQTT publish-on-change protocol
- Bidirectional ENTRY_B hardware swap
- Retire legacy `Mine-entry` / `Tracking-point-1` / `TareWb-App` when ready
