# Mines Entry (`mines_entry`) — Test Case Catalogue

**Application:** Mines-Checkpoint  
**Site profile:** `checkpoint_type = mines_entry`  
**Hardware focus:** Entry RFID, entry traffic light, entry boom, entry sensor  
**Modbus:** DI read **FC2**; DO write **FC5** (coil) or **FC6** (holding register 0/1)  

## Purpose

This document is the **expanded QA / UAT catalogue** for Mines Entry. It is intentionally long so non-technical stakeholders can see the real breadth of work: cloud APIs, RFID, ANPR, Modbus function codes (FC5 & FC6), timers, packaging, and field sign-off.

A shorter machine-oriented list also exists in `Mines_Entry_Test_Cases.csv`. Prefer **this Markdown** for reviews and audits.

## Summary counts

| Metric | Count |
|--------|------:|
| **Total test cases** | **273** |
| Modbus FC6 | 39 |
| Modbus FC5 | 37 |
| Setup | 29 |
| UAT | 25 |
| API | 17 |
| RFID | 17 |
| ANPR | 14 |
| Hardware | 14 |
| OCI | 14 |
| Manual | 10 |
| Sensor | 10 |
| E2E | 9 |
| Matrix | 8 |
| Display | 7 |
| Mobile RFID | 7 |
| Robustness | 6 |
| Modbus Mixed | 3 |
| Packaging | 3 |
| MQTT | 2 |
| Security | 2 |
| Priority P0 (go-live) | 132 |
| Priority P1 | 93 |

## Pin / function-code reference (mines_entry)

| Role | Address | Notes |
|------|--------:|-------|
| Entry sensor (DI) | 0 | Read **FC2** |
| TL Red (DO) | 0 | Write **FC5** or **FC6** |
| TL Green (DO) | 1 | Write **FC5** or **FC6** |
| Boom Open (DO) | 2 | Write **FC5** or **FC6** |
| Boom Close (DO) | 3 | Write **FC5** or **FC6** |

- **FC5** = Write Single Coil (ON/OFF).
- **FC6** = Write Single Register (`1` = ON, `0` = OFF in this application).
- Config key: `io_controller.digital_outputs.function_code` = `5` or `6`.

## How to use

1. Set environment (DEMO vs live, FC5 vs FC6).
2. Execute each case; record **Pass / Fail / Blocked** and evidence (log snippet, photo, capture).
3. P0 cases are go-live blockers; P1 should pass before production; P2/P3 as time allows.
4. UAT Sign-off section is for non-technical stakeholders to initial.

---

## Setup

### TC-ME-001 — checkpoint_type mines_entry loads Mines Entry branding

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-001` |
| **Module / Category** | Setup / Profile |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | iot_configuration.json present |
| **Test data** | `checkpoint_type=mines_entry` |
| **Expected result** | Service shows Mines Entry / ME branding; boom_close_style=entry |

**Steps:**

1. Set checkpoint_type=mines_entry
2. Start Mines-Checkpoint
3. Open dashboard / GET /api/status

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-002 — Reject / ignore wrong checkpoint_type when testing entry site

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-002` |
| **Module / Category** | Setup / Profile |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Site is physical mines entry |
| **Test data** | `checkpoint_type=tracking_1` |
| **Expected result** | OCI paths differ from mines_entry; do not use on entry site |

**Steps:**

1. Temporarily set tracking_1
2. Restart
3. Compare OCI paths

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-003 — Load .env DEMO_MODE=false for live hardware

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-003` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | .env configured |
| **Test data** | `DEMO_MODE=false` |
| **Expected result** | ModbusTCP connected (not DemoIO) |

**Steps:**

1. DEMO_MODE=false
2. Start app
3. Check logs

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-004 — DEMO_MODE=true uses in-memory I/O

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-004` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | .env |
| **Test data** | `DEMO_MODE=true` |
| **Expected result** | DemoIOController; simulate APIs work |

**Steps:**

1. DEMO_MODE=true
2. Start

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-005 — DEVICE_IP / device_ip from JSON used in OCI payloads

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-005` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | device_ip in JSON or .env |
| **Test data** | `device_ip=192.168.10.223` |
| **Expected result** | Payload device_ip matches config |

**Steps:**

1. Capture any OCI POST body

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-006 — API_HOST / API_PORT bind web dashboard

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-006` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | App start |
| **Test data** | `API_PORT=8080` |
| **Expected result** | Dashboard HTML loads (not static missing error) |

**Steps:**

1. Open http://127.0.0.1:API_PORT/

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-007 — MQTT_BROKER / MQTT_PORT for display

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-007` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Display MQTT up |
| **Test data** | `MQTT 1883` |
| **Expected result** | Display receives message |

**Steps:**

1. Trigger RFID ERR
2. Watch display topic

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-008 — OCI_BASE_URL and credentials load

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-008` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | .env OCI_* set |
| **Test data** | `OCI_BASE_URL` |
| **Expected result** | Calls OCI host with Basic Auth |

**Steps:**

1. Trigger RFID validate
2. Inspect request URL

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-009 — ANPR_BASE_URL separate from OCI

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-009` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | ANPR service up |
| **Test data** | `ANPR_BASE_URL` |
| **Expected result** | Detect hits ANPR host not OCI |

**Steps:**

1. Trigger ANPR
2. Inspect host

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-010 — API_DEBUG pause after OCI responses

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-010` |
| **Module / Category** | Setup / Env |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | API_DEBUG=true API_WAIT_AFTER_RESPONSE=5 |
| **Test data** | `5s wait` |
| **Expected result** | Log API_DEBUG waiting 5s after rfid-validate; ANPR not delayed |

**Steps:**

1. Trigger RFID validate
2. Watch logs

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-011 — iot_configuration.json loads without error

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-011` |
| **Module / Category** | Setup / JSON |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Valid JSON beside binary/source |
| **Test data** | `iot_configuration.json` |
| **Expected result** | Loaded IoT config log; no JSON parse error |

**Steps:**

1. Start app

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-012 — Corrupt iot_configuration.json

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-012` |
| **Module / Category** | Setup / JSON |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Backup good JSON |
| **Test data** | `Invalid JSON` |
| **Expected result** | App fails gracefully / logs error; site not silently misconfigured |

**Steps:**

1. Break JSON syntax
2. Start

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-013 — Missing iot_configuration.json

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-013` |
| **Module / Category** | Setup / JSON |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Rename file |
| **Test data** | `File missing` |
| **Expected result** | Warning or fallback; operator informed |

**Steps:**

1. Start app

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-014 — anpr_enabled true persisted

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-014` |
| **Module / Category** | Setup / JSON |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Dashboard ANPR toggle |
| **Test data** | `anpr_enabled=true` |
| **Expected result** | Remains true after restart |

**Steps:**

1. Enable ANPR
2. Restart app
3. GET /api/anpr-enabled

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-015 — anpr_enabled false persisted

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-015` |
| **Module / Category** | Setup / JSON |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Dashboard ANPR toggle |
| **Test data** | `anpr_enabled=false` |
| **Expected result** | Remains false; detect skipped |

**Steps:**

1. Disable ANPR
2. Restart

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-016 — Timer RFID_ERROR_DISPLAY_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-016` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env RFID_ERROR_DISPLAY_SEC=10 |
| **Test data** | `RFID_ERROR_DISPLAY_SEC=10` |
| **Expected result** | RFID ERR display duration matches configured 10s (±tolerance) |

**Steps:**

1. Set RFID_ERROR_DISPLAY_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-017 — Timer MANUAL_UPDATE_POLL_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-017` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env MANUAL_UPDATE_POLL_SEC=2 |
| **Test data** | `MANUAL_UPDATE_POLL_SEC=2` |
| **Expected result** | Fallback poll if truck_anpr_retry_timer missing matches configured 2s (±tolerance) |

**Steps:**

1. Set MANUAL_UPDATE_POLL_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-018 — Timer UPDATE_STATUS_2_RESET_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-018` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env UPDATE_STATUS_2_RESET_SEC=10 |
| **Test data** | `UPDATE_STATUS_2_RESET_SEC=10` |
| **Expected result** | Delay after vehicleStatus=2 matches configured 10s (±tolerance) |

**Steps:**

1. Set UPDATE_STATUS_2_RESET_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-019 — Timer RFID_COLLECT_WINDOW_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-019` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env RFID_COLLECT_WINDOW_SEC=2 |
| **Test data** | `RFID_COLLECT_WINDOW_SEC=2` |
| **Expected result** | RFID collect window matches configured 2s (±tolerance) |

**Steps:**

1. Set RFID_COLLECT_WINDOW_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-020 — Timer OCI_REQUEST_TIMEOUT_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-020` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env OCI_REQUEST_TIMEOUT_SEC=15 |
| **Test data** | `OCI_REQUEST_TIMEOUT_SEC=15` |
| **Expected result** | HTTP timeout to OCI matches configured 15s (±tolerance) |

**Steps:**

1. Set OCI_REQUEST_TIMEOUT_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-021 — Timer SENSOR_POLL_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-021` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env SENSOR_POLL_SEC=0.3 |
| **Test data** | `SENSOR_POLL_SEC=0.3` |
| **Expected result** | DI poll interval matches configured 0.3s (±tolerance) |

**Steps:**

1. Set SENSOR_POLL_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-022 — Timer MODBUS_TIMEOUT_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-022` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env MODBUS_TIMEOUT_SEC=1 |
| **Test data** | `MODBUS_TIMEOUT_SEC=1` |
| **Expected result** | Modbus TCP timeout matches configured 1s (±tolerance) |

**Steps:**

1. Set MODBUS_TIMEOUT_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-023 — Timer VEHICLE_CROSSING_TIMEOUT_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-023` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env VEHICLE_CROSSING_TIMEOUT_SEC=60 |
| **Test data** | `VEHICLE_CROSSING_TIMEOUT_SEC=60` |
| **Expected result** | Auto IDLE if no clear matches configured 60s (±tolerance) |

**Steps:**

1. Set VEHICLE_CROSSING_TIMEOUT_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-024 — Timer BOOM_CLOSE_DELAY_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-024` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env BOOM_CLOSE_DELAY_SEC=10 |
| **Test data** | `BOOM_CLOSE_DELAY_SEC=10` |
| **Expected result** | Boom stays open after clear matches configured 10s (±tolerance) |

**Steps:**

1. Set BOOM_CLOSE_DELAY_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-025 — Timer ANPR_API_MAX_RETRIES applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-025` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env ANPR_API_MAX_RETRIES=3 |
| **Test data** | `ANPR_API_MAX_RETRIES=3` |
| **Expected result** | ANPR retry count matches configured 3s (±tolerance) |

**Steps:**

1. Set ANPR_API_MAX_RETRIES
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-026 — Timer ANPR_API_RETRY_DELAY_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-026` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env ANPR_API_RETRY_DELAY_SEC=2 |
| **Test data** | `ANPR_API_RETRY_DELAY_SEC=2` |
| **Expected result** | Delay between ANPR retries matches configured 2s (±tolerance) |

**Steps:**

1. Set ANPR_API_RETRY_DELAY_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-027 — Timer ANPR_ERR_2_DISPLAY_SEC applied from .env

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-027` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | .env ANPR_ERR_2_DISPLAY_SEC=5 |
| **Test data** | `ANPR_ERR_2_DISPLAY_SEC=5` |
| **Expected result** | Display hold after ANPR fail path matches configured 5s (±tolerance) |

**Steps:**

1. Set ANPR_ERR_2_DISPLAY_SEC
2. Trigger related flow
3. Measure timing

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-028 — truck_anpr_retry_timer from iot_configuration

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-028` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | JSON truck_anpr_retry_timer=5 |
| **Test data** | `5` |
| **Expected result** | Polls ~every 5s |

**Steps:**

1. Force anpr_status=0
2. Measure status_check interval

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-029 — vehicle_crossing_timeout from JSON

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-029` |
| **Module / Category** | Setup / Timer |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | JSON timeout 30 |
| **Test data** | `30` |
| **Expected result** | Auto IDLE ~30s |

**Steps:**

1. Grant entry
2. Do not clear sensor

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## API

### TC-ME-030 — GET / returns dashboard or health

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-030` |
| **Module / Category** | API / Health |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | App running |
| **Test data** | `None` |
| **Expected result** | HTTP 200 HTML dashboard or health JSON |

**Steps:**

1. GET /

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-031 — GET /api/status IDLE snapshot

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-031` |
| **Module / Category** | API / Status |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | State IDLE |
| **Test data** | `None` |
| **Expected result** | state=IDLE; demo_mode; anpr_enabled; hardware fields |

**Steps:**

1. GET /api/status

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-032 — GET /api/status during WAIT_CROSSING

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-032` |
| **Module / Category** | API / Status |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | After grant |
| **Test data** | `None` |
| **Expected result** | state=WAIT_CROSSING; transaction fields present |

**Steps:**

1. GET /api/status

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-033 — POST /api/reset forces IDLE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-033` |
| **Module / Category** | API / Reset |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Any busy state |
| **Test data** | `{}` |
| **Expected result** | IDLE; TL red; boom closed; RFID prepare IDLE |

**Steps:**

1. POST /api/reset

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-034 — Double reset is safe

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-034` |
| **Module / Category** | API / Reset |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | Already IDLE |
| **Test data** | `{}` |
| **Expected result** | Still IDLE; no crash |

**Steps:**

1. POST /api/reset twice

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-035 — POST /api/simulate-exit in DEMO

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-035` |
| **Module / Category** | API / Simulate |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | DEMO_MODE; WAIT_CROSSING |
| **Test data** | `{}` |
| **Expected result** | Sensor pulse; eventually IDLE |

**Steps:**

1. POST /api/simulate-exit

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-036 — GET /api/anpr-enabled

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-036` |
| **Module / Category** | API / ANPR toggle |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | App up |
| **Test data** | `None` |
| **Expected result** | JSON anpr_enabled bool |

**Steps:**

1. GET endpoint

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-037 — POST enable ANPR

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-037` |
| **Module / Category** | API / ANPR toggle |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Operator logged in if required |
| **Test data** | `true` |
| **Expected result** | Persisted; detect used next cycle |

**Steps:**

1. POST anpr_enabled=true

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-038 — POST disable ANPR

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-038` |
| **Module / Category** | API / ANPR toggle |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | App up |
| **Test data** | `false` |
| **Expected result** | Detect skipped; invalid-truck anpr_status=2 then status_check |

**Steps:**

1. POST anpr_enabled=false

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-039 — POST missing anpr_enabled field

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-039` |
| **Module / Category** | API / ANPR toggle |
| **Priority / Type** | P2 / Negative |
| **Preconditions** | App up |
| **Test data** | `{}` |
| **Expected result** | HTTP 400 anpr_enabled required |

**Steps:**

1. POST {}

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-040 — Operator login success

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-040` |
| **Module / Category** | API / Operator |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | OPERATOR_USERNAME/PASSWORD set |
| **Test data** | `admin/gmdc@123` |
| **Expected result** | Login success; Free Pass / Reset enabled |

**Steps:**

1. POST login with correct creds

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-041 — Operator login wrong password

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-041` |
| **Module / Category** | API / Operator |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | App up |
| **Test data** | `bad` |
| **Expected result** | Rejected; Free Pass stays disabled |

**Steps:**

1. POST wrong password

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-042 — Free pass opens gate when authorized

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-042` |
| **Module / Category** | API / Free Pass |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Logged in; IDLE |
| **Test data** | `None` |
| **Expected result** | Boom open / TL green path or documented free-pass behavior |

**Steps:**

1. Trigger free pass

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-043 — Free pass blocked when not logged in

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-043` |
| **Module / Category** | API / Free Pass |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Not logged in |
| **Test data** | `None` |
| **Expected result** | Rejected / disabled |

**Steps:**

1. Trigger free pass

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-044 — Dashboard static/web assets load

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-044` |
| **Module / Category** | API / Static |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Frozen or source run |
| **Test data** | `static/web` |
| **Expected result** | No Static directory not found error |

**Steps:**

1. Open /
2. Check CSS/JS network

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-045 — CORS allows dashboard XHR

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-045` |
| **Module / Category** | API / CORS |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | Browser dashboard |
| **Test data** | `None` |
| **Expected result** | Requests succeed |

**Steps:**

1. Call /api/status from page

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-046 — Version / service name endpoint if present

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-046` |
| **Module / Category** | API / Version |
| **Priority / Type** | P3 / Positive |
| **Preconditions** | App up |
| **Test data** | `None` |
| **Expected result** | service reflects Mines Checkpoint / Entry |

**Steps:**

1. GET version or status

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## RFID

### TC-ME-047 — POST /rfid_data valid Zebra TAG list

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-047` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | IDLE; OCI up |
| **Test data** | `E200… tag` |
| **Expected result** | HTTP 200; cloud stop; OCI validate starts |

**Steps:**

1. POST tag list with idHex

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-048 — Empty tag list rejected

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-048` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | IDLE |
| **Test data** | `[]` |
| **Expected result** | HTTP 400 No idHex tags |

**Steps:**

1. POST []

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-049 — Invalid JSON rejected

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-049` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P2 / Negative |
| **Preconditions** | IDLE |
| **Test data** | `raw text` |
| **Expected result** | HTTP 400 |

**Steps:**

1. POST not-json

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-050 — Ignore RFID when not IDLE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-050` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | WAIT_CROSSING |
| **Test data** | `valid` |
| **Expected result** | Ignored; log state |

**Steps:**

1. POST valid tags

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-051 — Ignore RFID during MANUAL_UPDATE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-051` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Manual loop |
| **Test data** | `valid` |
| **Expected result** | Ignored |

**Steps:**

1. POST tags

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-052 — Ignore RFID during RFID_VALIDATE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-052` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Mid validate |
| **Test data** | `valid` |
| **Expected result** | Second ignored / busy |

**Steps:**

1. POST second tag quickly

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-053 — /rfid_management keepalive

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-053` |
| **Module / Category** | RFID / Reader |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | App up |
| **Test data** | `{}` |
| **Expected result** | HTTP 200 success |

**Steps:**

1. POST /rfid_management

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-054 — /api/read-rfid accepts tags

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-054` |
| **Module / Category** | RFID / Alias |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `valid tags` |
| **Expected result** | Same as /rfid_data |

**Steps:**

1. POST alias

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-055 — /read_rfid accepts tags

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-055` |
| **Module / Category** | RFID / Alias |
| **Priority / Type** | P3 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `valid tags` |
| **Expected result** | Same as /rfid_data |

**Steps:**

1. POST alias

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-056 — Accept lowercase idHex

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-056` |
| **Module / Category** | RFID / Format |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `e200…` |
| **Expected result** | Accepted / normalized |

**Steps:**

1. POST lowercase hex

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-057 — Accept multiple tags pick first policy

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-057` |
| **Module / Category** | RFID / Format |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `two idHex` |
| **Expected result** | Documented selection; cycle starts once |

**Steps:**

1. POST 2+ tags

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-058 — TAG without idHex ignored

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-058` |
| **Module / Category** | RFID / Format |
| **Priority / Type** | P2 / Negative |
| **Preconditions** | IDLE |
| **Test data** | `{}` |
| **Expected result** | 400 or no tags |

**Steps:**

1. POST type TAG no idHex

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-059 — IDLE prepare login/mode/start

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-059` |
| **Module / Category** | RFID / Cloud |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | API mode; reader HTTPS |
| **Test data** | `reader IP` |
| **Expected result** | localRestLogin then start; scanning |

**Steps:**

1. Reset to IDLE

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-060 — Stop reader after tags

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-060` |
| **Module / Category** | RFID / Cloud |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Tags received |
| **Test data** | `valid` |
| **Expected result** | cloud/stop before OCI |

**Steps:**

1. POST /rfid_data

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-061 — API mode no TCP :5555 client

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-061` |
| **Module / Category** | RFID / Cloud |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mode=API DEMO=false |
| **Test data** | `mode API` |
| **Expected result** | No TCP connect retries to 5555 |

**Steps:**

1. Start app watch logs

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-062 — Reader unreachable on IDLE prepare

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-062` |
| **Module / Category** | RFID / Cloud |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Wrong reader IP |
| **Test data** | `bad IP` |
| **Expected result** | Error logged; app stays up |

**Steps:**

1. Start / reset

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-063 — Wrong RFID_USERNAME/PASSWORD

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-063` |
| **Module / Category** | RFID / Cloud |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Bad Basic Auth |
| **Test data** | `wrong pass` |
| **Expected result** | Login fail logged |

**Steps:**

1. IDLE prepare

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Mobile RFID

### TC-ME-064 — Valid mobile RFID returns OCI body

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-064` |
| **Module / Category** | Mobile RFID / API |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | IDLE; OCI up |
| **Test data** | `{"rfid_data":"…"}` |
| **Expected result** | HTTP 200 OCI validate JSON |

**Steps:**

1. POST /rfid_data_from_mobile_app

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-065 — Missing rfid_data key

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-065` |
| **Module / Category** | Mobile RFID / API |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | IDLE |
| **Test data** | `{}` |
| **Expected result** | HTTP 500 Error rfid_data |

**Steps:**

1. POST {}

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-066 — Blank rfid_data

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-066` |
| **Module / Category** | Mobile RFID / API |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | IDLE |
| **Test data** | `{"rfid_data":"  "}` |
| **Expected result** | HTTP 500 blank value |

**Steps:**

1. POST blank

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-067 — Null rfid_data

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-067` |
| **Module / Category** | Mobile RFID / API |
| **Priority / Type** | P2 / Negative |
| **Preconditions** | IDLE |
| **Test data** | `{"rfid_data":null}` |
| **Expected result** | HTTP 500 |

**Steps:**

1. POST null

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-068 — Valid mobile continues to ANPR

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-068` |
| **Module / Category** | Mobile RFID / Workflow |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | OCI 200 |
| **Test data** | `valid` |
| **Expected result** | Background ANPR then grant/manual |

**Steps:**

1. POST mobile RFID
2. Observe ANPR

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-069 — Invalid mobile shows RFID ERR 1

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-069` |
| **Module / Category** | Mobile RFID / Workflow |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | OCI 500 |
| **Test data** | `BADTAG` |
| **Expected result** | Display RFID ERR 1; ~10s IDLE |

**Steps:**

1. POST bad tag

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-070 — Mobile while workflow busy

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-070` |
| **Module / Category** | Mobile RFID / Busy |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Cycle running |
| **Test data** | `valid` |
| **Expected result** | 500 busy or ignored |

**Steps:**

1. POST mobile

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## OCI

### TC-ME-071 — Validate success parses truck_details

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-071` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Valid RFID |
| **Test data** | `T|… pipe string` |
| **Expected result** | vehicle_no token set; display truck |

**Steps:**

1. Complete RFID validate

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-072 — Validate failure RFID ERR 1

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-072` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Bad RFID |
| **Test data** | `status 500` |
| **Expected result** | Display RFID ERR 1; boom closed; IDLE after timer |

**Steps:**

1. Trigger validate fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-073 — Payload contains rfid + device_ip

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-073` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Any cycle |
| **Test data** | `rfid, device_ip` |
| **Expected result** | Both fields present |

**Steps:**

1. Capture request

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-074 — OCI timeout / unreachable

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-074` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | Block OCI host |
| **Test data** | `timeout` |
| **Expected result** | Error path; no boom open; recovers to IDLE |

**Steps:**

1. Trigger RFID

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-075 — Wrong OCI credentials

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-075` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Bad user/pass |
| **Test data** | `401/403` |
| **Expected result** | Auth failure handled; no grant |

**Steps:**

1. Trigger RFID

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-076 — mines_entry rfid-tag path used

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-076` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry profile |
| **Test data** | `/dlms_checkpoint/rfid-tag` |
| **Expected result** | URL matches entry path not tracking |

**Steps:**

1. Capture URL

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-077 — CE| truck_details prefix detected

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-077` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | OCI returns CE|… |
| **Test data** | `CE|…` |
| **Expected result** | Later CE check-status loop used |

**Steps:**

1. RFID validate

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-078 — T| truck_details normal path

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-078` |
| **Module / Category** | OCI / RFID |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | OCI returns T|… |
| **Test data** | `T|…` |
| **Expected result** | Non-CE status_check / grant rules |

**Steps:**

1. RFID validate

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## ANPR

### TC-ME-079 — anpr_status=1 happy grant path

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-079` |
| **Module / Category** | ANPR / Detect |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | RFID valid; ANPR on |
| **Test data** | `{"anpr_status":1}` |
| **Expected result** | invalid-truck; boom-close; boom OPEN TL GREEN; WAIT_CROSSING |

**Steps:**

1. ANPR returns 1
2. Observe HW

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-080 — anpr_status=0 enters status_check

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-080` |
| **Module / Category** | ANPR / Detect |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | RFID valid |
| **Test data** | `{"anpr_status":0}` |
| **Expected result** | invalid-truck; ANPR ERR; poll status_check |

**Steps:**

1. ANPR 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-081 — anpr_status=2 enters status_check

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-081` |
| **Module / Category** | ANPR / Detect |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | RFID valid |
| **Test data** | `{"anpr_status":2}` |
| **Expected result** | invalid-truck; ANPR Err-2; poll status_check |

**Steps:**

1. ANPR 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-082 — ANPR disabled skips detect still status_check

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-082` |
| **Module / Category** | ANPR / Detect |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | anpr_enabled=false |
| **Test data** | `stub anpr_status=2` |
| **Expected result** | No /api/detect; invalid-truck(2); status_check mandatory |

**Steps:**

1. Valid RFID cycle

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-083 — ANPR disabled does not auto-grant without status_check

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-083` |
| **Module / Category** | ANPR / Detect |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | anpr_enabled=false; non-CE |
| **Test data** | `anpr off` |
| **Expected result** | Must call status_check before boom open |

**Steps:**

1. RFID valid
2. Watch OCI calls

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-084 — ANPR exception retries 3 times

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-084` |
| **Module / Category** | ANPR / Retry |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | ANPR down |
| **Test data** | `unreachable` |
| **Expected result** | 3 attempts ~2s; ANPR API ERR; IDLE; boom closed |

**Steps:**

1. Force connection errors

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-085 — ANPR succeeds on 2nd attempt

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-085` |
| **Module / Category** | ANPR / Retry |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | First fail second ok |
| **Test data** | `fail then status 1` |
| **Expected result** | Grant after 2 detect calls |

**Steps:**

1. Simulate flake

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-086 — ANPR succeeds on 3rd attempt

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-086` |
| **Module / Category** | ANPR / Retry |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | Two fails then ok |
| **Test data** | `fail fail ok` |
| **Expected result** | Grant after 3 detect calls |

**Steps:**

1. Simulate

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-087 — ANPR Basic Auth separate

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-087` |
| **Module / Category** | ANPR / Auth |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | ANPR_USERNAME set |
| **Test data** | `Basic Auth` |
| **Expected result** | Auth header uses ANPR creds |

**Steps:**

1. Capture /api/detect

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-088 — Wrong ANPR password

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-088` |
| **Module / Category** | ANPR / Auth |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Bad ANPR pass |
| **Test data** | `401` |
| **Expected result** | Retry/fail path; no silent grant |

**Steps:**

1. Trigger detect

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-089 — Detect payload has vehicle_number + rfid

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-089` |
| **Module / Category** | ANPR / Payload |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | RFID valid |
| **Test data** | `vehicle_number,rfid` |
| **Expected result** | Both present; token/device_ip if configured |

**Steps:**

1. Capture detect body

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-090 — Always POST invalid-truck after ANPR (or stub)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-090` |
| **Module / Category** | ANPR / Invalid-truck |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Any ANPR outcome |
| **Test data** | `anpr_status 0/1/2` |
| **Expected result** | Called once before grant/manual |

**Steps:**

1. Capture invalid-truck

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-091 — invalid-truck filtered fields only

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-091` |
| **Module / Category** | ANPR / Invalid-truck |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | ANPR raw large |
| **Test data** | `filtered keys` |
| **Expected result** | Only contract fields; no secrets |

**Steps:**

1. Capture body

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-092 — invalid-truck OCI down

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-092` |
| **Module / Category** | ANPR / Invalid-truck |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | Block invalid-truck URL |
| **Test data** | `timeout` |
| **Expected result** | UI shows API failure; no boom open |

**Steps:**

1. Force ANPR 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Manual

### TC-ME-093 — vehicleStatus=0 keeps polling

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-093` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | MANUAL after 0/2 |
| **Test data** | `{"vehicleStatus":0}` |
| **Expected result** | Stay in loop; continue polling |

**Steps:**

1. Return vehicleStatus 0 repeatedly

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-094 — vehicleStatus=1 grants entry

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-094` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | MANUAL |
| **Test data** | `{"vehicleStatus":1}` |
| **Expected result** | boom-close; boom OPEN TL GREEN; WAIT_CROSSING |

**Steps:**

1. Return vehicleStatus 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-095 — vehicleStatus=2 resets IDLE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-095` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | MANUAL |
| **Test data** | `{"vehicleStatus":2}` |
| **Expected result** | After delay IDLE; boom closed TL red |

**Steps:**

1. Return vehicleStatus 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-096 — HTTP 200 without vehicleStatus treated as retry

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-096` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | MANUAL |
| **Test data** | `{"statusCode":200}` |
| **Expected result** | Does not grant; keeps polling |

**Steps:**

1. Return statusCode 200 only

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-097 — status_check transport failure alert once

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-097` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | MANUAL; OCI down |
| **Test data** | `timeout` |
| **Expected result** | Operator alert; continue or documented recovery |

**Steps:**

1. Fail status_check

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-098 — Poll interval matches truck_anpr_retry_timer

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-098` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | timer=5 |
| **Test data** | `5s` |
| **Expected result** | ~5s between POSTs |

**Steps:**

1. Measure gaps

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-099 — Reset during manual loop

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-099` |
| **Module / Category** | Manual / status_check |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | MANUAL polling |
| **Test data** | `{}` |
| **Expected result** | Exit loop; IDLE hardware |

**Steps:**

1. POST /api/reset

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-100 — CE trip polls until statusCode 200 even on ANPR 1

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-100` |
| **Module / Category** | Manual / CE |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | CE| truck_details; ANPR 1 |
| **Test data** | `statusCode 100 then 200` |
| **Expected result** | Grant only after statusCode 200 |

**Steps:**

1. status_check pending then 200

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-101 — CE mismatch ignores vehicleStatus=2 abort semantics

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-101` |
| **Module / Category** | Manual / CE |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | CE| ANPR 0 |
| **Test data** | `mixed` |
| **Expected result** | Continues until statusCode 200 (per CE rules) |

**Steps:**

1. Return vehicleStatus 2 but statusCode not 200

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-102 — CE ANPR disabled still CE status loop

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-102` |
| **Module / Category** | Manual / CE |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | CE|; anpr off |
| **Test data** | `CE stub` |
| **Expected result** | invalid-truck then CE check-status loop |

**Steps:**

1. RFID valid

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## OCI

### TC-ME-103 — boom-close 200 opens boom

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-103` |
| **Module / Category** | OCI / Boom-close |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Grant path |
| **Test data** | `{"status":200}` |
| **Expected result** | Boom OPEN; TL GREEN |

**Steps:**

1. boom-close status 200

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-104 — boom-close 500 does not open

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-104` |
| **Module / Category** | OCI / Boom-close |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | Grant path |
| **Test data** | `{"status":500}` |
| **Expected result** | Boom stays closed; log NOT opened |

**Steps:**

1. boom-close 500

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-105 — Payload rfid device_ip close-type=auto

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-105` |
| **Module / Category** | OCI / Boom-close |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Grant |
| **Test data** | `close-type=auto` |
| **Expected result** | Fields present; entry style truck_details |

**Steps:**

1. Capture body

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-106 — mines_entry boom-close path

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-106` |
| **Module / Category** | OCI / Boom-close |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | mines_entry |
| **Test data** | `/dlms_checkpoint/boom-close` |
| **Expected result** | Not tracking checkpoint_boom_close |

**Steps:**

1. Capture URL

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-107 — boom-close unreachable

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-107` |
| **Module / Category** | OCI / Boom-close |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | Block URL |
| **Test data** | `timeout` |
| **Expected result** | No hardware open; error UI |

**Steps:**

1. Grant path

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-108 — reset_checkpoint called on IDLE reset

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-108` |
| **Module / Category** | OCI / Reset |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | Reset API |
| **Test data** | `reset_checkpoint` |
| **Expected result** | OCI reset called when configured |

**Steps:**

1. POST /api/reset
2. Capture OCI

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Display

### TC-ME-109 — Display publishes: RFID ERR 1

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-109` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | RFID invalid |
| **Test data** | `RFID ERR 1` |
| **Expected result** | Message contains RFID ERR 1 (or truck + Entry Granted) |

**Steps:**

1. Trigger path
2. Read MQTT / console display

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-110 — Display publishes: Truck number

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-110` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | RFID valid |
| **Test data** | `Truck number` |
| **Expected result** | Message contains Truck number (or truck + Entry Granted) |

**Steps:**

1. Trigger path
2. Read MQTT / console display

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-111 — Display publishes: ANPR ERR / mismatch

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-111` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | anpr_status=0 |
| **Test data** | `ANPR ERR / mismatch` |
| **Expected result** | Message contains ANPR ERR / mismatch (or truck + Entry Granted) |

**Steps:**

1. Trigger path
2. Read MQTT / console display

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-112 — Display publishes: ANPR Err-2

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-112` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | anpr_status=2 |
| **Test data** | `ANPR Err-2` |
| **Expected result** | Message contains ANPR Err-2 (or truck + Entry Granted) |

**Steps:**

1. Trigger path
2. Read MQTT / console display

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-113 — Display publishes: ANPR API ERR

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-113` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | ANPR down |
| **Test data** | `ANPR API ERR` |
| **Expected result** | Message contains ANPR API ERR (or truck + Entry Granted) |

**Steps:**

1. Trigger path
2. Read MQTT / console display

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-114 — Display publishes: Entry Granted

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-114` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Grant success |
| **Test data** | `Entry Granted` |
| **Expected result** | Message contains Entry Granted (or truck + Entry Granted) |

**Steps:**

1. Trigger path
2. Read MQTT / console display

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-115 — Display broker down does not crash app

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-115` |
| **Module / Category** | Display / MQTT |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Wrong MQTT broker |
| **Test data** | `bad broker` |
| **Expected result** | App continues; display demo/fallback |

**Steps:**

1. Start + RFID cycle

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Sensor

### TC-ME-116 — IDLE sensor FALSE no action

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-116` |
| **Module / Category** | Sensor / Crossing |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | IDLE boom closed |
| **Test data** | `FALSE` |
| **Expected result** | No boom/TL change |

**Steps:**

1. Keep DI false

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-117 — IDLE pulse ignored

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-117` |
| **Module / Category** | Sensor / Crossing |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `pulse` |
| **Expected result** | No reset side effects |

**Steps:**

1. TRUE then FALSE while IDLE

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-118 — During validation pulse ignored

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-118` |
| **Module / Category** | Sensor / Crossing |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | RFID/ANPR running |
| **Test data** | `pulse` |
| **Expected result** | Cycle continues |

**Steps:**

1. Pulse sensor

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-119 — After grant TRUE then FALSE clears

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-119` |
| **Module / Category** | Sensor / Crossing |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | WAIT_CROSSING boom open |
| **Test data** | `falling after occupied` |
| **Expected result** | Delayed boom close; TL red; IDLE |

**Steps:**

1. Sensor TRUE
2. Sensor FALSE

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-120 — Rising edge alone does not close

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-120` |
| **Module / Category** | Sensor / Crossing |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | WAIT_CROSSING |
| **Test data** | `TRUE` |
| **Expected result** | Boom remains OPEN |

**Steps:**

1. Sensor TRUE hold

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-121 — Crossing timeout auto IDLE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-121` |
| **Module / Category** | Sensor / Timeout |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | WAIT_CROSSING; timeout set |
| **Test data** | `60s` |
| **Expected result** | Auto IDLE boom closed TL red |

**Steps:**

1. Never clear sensor

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-122 — BOOM_CLOSE_DELAY_SEC after clear

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-122` |
| **Module / Category** | Sensor / Delay |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | WAIT_CROSSING; delay=10 |
| **Test data** | `10s` |
| **Expected result** | Boom closes ~10s after clear |

**Steps:**

1. Clear sensor
2. Time boom close

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-123 — entry_sensor uses DI pin 0

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-123` |
| **Module / Category** | Sensor / Mapping |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Config mapping |
| **Test data** | `DI0` |
| **Expected result** | Only entry sensor reacts |

**Steps:**

1. Toggle DI0 only

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-124 — WB/exit sensors disabled for mines_entry

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-124` |
| **Module / Category** | Sensor / Mapping |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | mines_entry JSON |
| **Test data** | `DI1/DI2` |
| **Expected result** | No workflow effect |

**Steps:**

1. Toggle unused DI

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-125 — default_signal low idle FALSE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-125` |
| **Module / Category** | Sensor / Polarity |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Config default_signal=low |
| **Test data** | `low` |
| **Expected result** | Reported unoccupied |

**Steps:**

1. Idle read

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Hardware

### TC-ME-126 — IDLE: red ON green OFF

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-126` |
| **Module / Category** | Hardware / TL |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | App start/reset |
| **Test data** | `IDLE` |
| **Expected result** | Red asserted green off |

**Steps:**

1. Measure DO0/DO1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-127 — Grant: green ON red OFF

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-127` |
| **Module / Category** | Hardware / TL |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Grant path |
| **Test data** | `grant` |
| **Expected result** | Green asserted red off |

**Steps:**

1. Measure DO0/DO1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-128 — Never both red and green ON long-term

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-128` |
| **Module / Category** | Hardware / TL |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Any transition |
| **Test data** | `TL` |
| **Expected result** | Interlock: no sustained both-ON |

**Steps:**

1. Observe during switch

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-129 — IDLE boom close asserted

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-129` |
| **Module / Category** | Hardware / Boom |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `close` |
| **Expected result** | close_pin ON open_pin OFF (direct mode) |

**Steps:**

1. Measure DO2/DO3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-130 — Grant boom open asserted

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-130` |
| **Module / Category** | Hardware / Boom |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Grant |
| **Test data** | `open` |
| **Expected result** | open_pin ON close_pin OFF |

**Steps:**

1. Measure DO2/DO3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-131 — After clear boom returns closed

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-131` |
| **Module / Category** | Hardware / Boom |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Post crossing |
| **Test data** | `closed` |
| **Expected result** | Close asserted again |

**Steps:**

1. After delay measure

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-132 — Pin map DO0 red DO1 green DO2 open DO3 close

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-132` |
| **Module / Category** | Hardware / Pins |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry JSON |
| **Test data** | `0/1/2/3` |
| **Expected result** | Log matches mapping |

**Steps:**

1. Check startup Hardware mapped log

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-133 — Connect controller DEMO false

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-133` |
| **Module / Category** | Hardware / Modbus |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Controller 502 up |
| **Test data** | `host:502 slave=1` |
| **Expected result** | ModbusTCP connected read_fc=2 write_fc configured |

**Steps:**

1. Start app

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-134 — Wrong Modbus IP

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-134` |
| **Module / Category** | Hardware / Modbus |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | Bad IP |
| **Test data** | `bad IP` |
| **Expected result** | Connect fail logged; no silent DemoIO unless DEMO true |

**Steps:**

1. Start DEMO=false

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-135 — Wrong slave id

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-135` |
| **Module / Category** | Hardware / Modbus |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | slave mismatch |
| **Test data** | `slave=2 vs 1` |
| **Expected result** | Reads/writes fail or wrong; documented |

**Steps:**

1. Start

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-136 — Controller power cycle mid-run

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-136` |
| **Module / Category** | Hardware / Modbus |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | App running |
| **Test data** | `reconnect` |
| **Expected result** | Resync after failures; recovers or safe IDLE |

**Steps:**

1. Power cycle PLC
2. Continue cycle

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-137 — Read DI via FC2 discrete inputs

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-137` |
| **Module / Category** | Hardware / DI |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Real controller |
| **Test data** | `read_fc=2` |
| **Expected result** | Sensor via FC2 addr 0 |

**Steps:**

1. Monitor with tool

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-138 — FC2 read all 8 inputs range

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-138` |
| **Module / Category** | Hardware / DI |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | di count=8 |
| **Test data** | `0/8` |
| **Expected result** | No exception; unused inputs ignored |

**Steps:**

1. Poll DI0-7

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-139 — FC2 timeout handling

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-139` |
| **Module / Category** | Hardware / DI |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Induce timeout |
| **Test data** | `timeout` |
| **Expected result** | Logged; resync path |

**Steps:**

1. Pull network briefly

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Modbus FC5

### TC-ME-140 — FC5 write coil ON for entry_tl_red (DO0)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-140` |
| **Module / Category** | Modbus FC5 / Write ON |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; DEMO=false; controller up |
| **Test data** | `FC5 addr=0 value=ON` |
| **Expected result** | Controller coil 0 ON; field device shows Traffic light RED |

**Steps:**

1. Configure digital_outputs.function_code=5
2. Trigger app action that asserts Traffic light RED
3. Capture Modbus FC5 to address 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-141 — FC5 write coil OFF for entry_tl_red (DO0)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-141` |
| **Module / Category** | Modbus FC5 / Write OFF |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5 |
| **Test data** | `FC5 addr=0 value=OFF` |
| **Expected result** | Coil 0 OFF |

**Steps:**

1. Assert then de-assert Traffic light RED
2. Capture FC5 OFF to addr 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-142 — FC5 entry_tl_red verified with independent Modbus client

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-142` |
| **Module / Category** | Modbus FC5 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; second client FC1/FC2 or coil read |
| **Test data** | `DO0` |
| **Expected result** | External read matches app intent |

**Steps:**

1. App writes DO0
2. External tool reads coil 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-143 — FC5 write failure to entry_tl_red logged

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-143` |
| **Module / Category** | Modbus FC5 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Disconnect DO path or force exception |
| **Test data** | `DO0` |
| **Expected result** | write failed logged; app does not claim success |

**Steps:**

1. Break write
2. Trigger Traffic light RED

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-144 — FC5 write coil ON for entry_tl_green (DO1)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-144` |
| **Module / Category** | Modbus FC5 / Write ON |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; DEMO=false; controller up |
| **Test data** | `FC5 addr=1 value=ON` |
| **Expected result** | Controller coil 1 ON; field device shows Traffic light GREEN |

**Steps:**

1. Configure digital_outputs.function_code=5
2. Trigger app action that asserts Traffic light GREEN
3. Capture Modbus FC5 to address 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-145 — FC5 write coil OFF for entry_tl_green (DO1)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-145` |
| **Module / Category** | Modbus FC5 / Write OFF |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5 |
| **Test data** | `FC5 addr=1 value=OFF` |
| **Expected result** | Coil 1 OFF |

**Steps:**

1. Assert then de-assert Traffic light GREEN
2. Capture FC5 OFF to addr 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-146 — FC5 entry_tl_green verified with independent Modbus client

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-146` |
| **Module / Category** | Modbus FC5 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; second client FC1/FC2 or coil read |
| **Test data** | `DO1` |
| **Expected result** | External read matches app intent |

**Steps:**

1. App writes DO1
2. External tool reads coil 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-147 — FC5 write failure to entry_tl_green logged

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-147` |
| **Module / Category** | Modbus FC5 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Disconnect DO path or force exception |
| **Test data** | `DO1` |
| **Expected result** | write failed logged; app does not claim success |

**Steps:**

1. Break write
2. Trigger Traffic light GREEN

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-148 — FC5 write coil ON for entry_boom_open (DO2)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-148` |
| **Module / Category** | Modbus FC5 / Write ON |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; DEMO=false; controller up |
| **Test data** | `FC5 addr=2 value=ON` |
| **Expected result** | Controller coil 2 ON; field device shows Boom OPEN |

**Steps:**

1. Configure digital_outputs.function_code=5
2. Trigger app action that asserts Boom OPEN
3. Capture Modbus FC5 to address 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-149 — FC5 write coil OFF for entry_boom_open (DO2)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-149` |
| **Module / Category** | Modbus FC5 / Write OFF |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5 |
| **Test data** | `FC5 addr=2 value=OFF` |
| **Expected result** | Coil 2 OFF |

**Steps:**

1. Assert then de-assert Boom OPEN
2. Capture FC5 OFF to addr 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-150 — FC5 entry_boom_open verified with independent Modbus client

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-150` |
| **Module / Category** | Modbus FC5 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; second client FC1/FC2 or coil read |
| **Test data** | `DO2` |
| **Expected result** | External read matches app intent |

**Steps:**

1. App writes DO2
2. External tool reads coil 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-151 — FC5 write failure to entry_boom_open logged

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-151` |
| **Module / Category** | Modbus FC5 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Disconnect DO path or force exception |
| **Test data** | `DO2` |
| **Expected result** | write failed logged; app does not claim success |

**Steps:**

1. Break write
2. Trigger Boom OPEN

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-152 — FC5 write coil ON for entry_boom_close (DO3)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-152` |
| **Module / Category** | Modbus FC5 / Write ON |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; DEMO=false; controller up |
| **Test data** | `FC5 addr=3 value=ON` |
| **Expected result** | Controller coil 3 ON; field device shows Boom CLOSE |

**Steps:**

1. Configure digital_outputs.function_code=5
2. Trigger app action that asserts Boom CLOSE
3. Capture Modbus FC5 to address 3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-153 — FC5 write coil OFF for entry_boom_close (DO3)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-153` |
| **Module / Category** | Modbus FC5 / Write OFF |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5 |
| **Test data** | `FC5 addr=3 value=OFF` |
| **Expected result** | Coil 3 OFF |

**Steps:**

1. Assert then de-assert Boom CLOSE
2. Capture FC5 OFF to addr 3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-154 — FC5 entry_boom_close verified with independent Modbus client

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-154` |
| **Module / Category** | Modbus FC5 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; second client FC1/FC2 or coil read |
| **Test data** | `DO3` |
| **Expected result** | External read matches app intent |

**Steps:**

1. App writes DO3
2. External tool reads coil 3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-155 — FC5 write failure to entry_boom_close logged

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-155` |
| **Module / Category** | Modbus FC5 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Disconnect DO path or force exception |
| **Test data** | `DO3` |
| **Expected result** | write failed logged; app does not claim success |

**Steps:**

1. Break write
2. Trigger Boom CLOSE

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-156 — FC5 IDLE sequence: red ON, green OFF, open OFF, close ON

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-156` |
| **Module / Category** | Modbus FC5 / Sequence |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; reset IDLE |
| **Test data** | `DO0=1 DO1=0 DO2=0 DO3=1` |
| **Expected result** | Final coil state matches idle safety |

**Steps:**

1. Reset to IDLE
2. Capture 4 coil writes order

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-157 — FC5 GRANT sequence: red OFF, green ON, open ON, close OFF

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-157` |
| **Module / Category** | Modbus FC5 / Sequence |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; grant path |
| **Test data** | `DO0=0 DO1=1 DO2=1 DO3=0` |
| **Expected result** | Gate open + green |

**Steps:**

1. Complete grant
2. Capture coil writes

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-158 — FC5 CLEAR sequence returns to idle coils

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-158` |
| **Module / Category** | Modbus FC5 / Sequence |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5; after sensor clear + delay |
| **Test data** | `back to idle pattern` |
| **Expected result** | Safe idle coils restored |

**Steps:**

1. Complete crossing clear
2. Capture coils

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-159 — FC5 rapid red↔green transitions no stuck coil

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-159` |
| **Module / Category** | Modbus FC5 / Sequence |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5 |
| **Test data** | `multiple cycles` |
| **Expected result** | Each cycle ends with correct idle coils |

**Steps:**

1. Reset
2. Grant
3. Reset again quickly

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-160 — FC5 boom open/close mutual exclusion

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-160` |
| **Module / Category** | Modbus FC5 / Sequence |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | write_fc=5; grant then clear |
| **Test data** | `DO2/DO3` |
| **Expected result** | No sustained both-ON (interlock) |

**Steps:**

1. Observe DO2 and DO3 never both ON longer than transition

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-161 — FC5 respects do_start offset 0

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-161` |
| **Module / Category** | Modbus FC5 / Address |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | do_start=0 write_fc=5 |
| **Test data** | `start=0` |
| **Expected result** | FC5 to address 0 |

**Steps:**

1. Write red
2. Confirm absolute address 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-162 — FC5 with non-zero do_start offset

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-162` |
| **Module / Category** | Modbus FC5 / Address |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | If site uses do_start≠0 |
| **Test data** | `do_start=8 pin0 → addr 8` |
| **Expected result** | FC5 hits absolute address start+pin |

**Steps:**

1. Set do_start=8
2. Map pins
3. Write red

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-163 — FC5 uses configured slave_id

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-163` |
| **Module / Category** | Modbus FC5 / Slave |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | slave_id=1 write_fc=5 |
| **Test data** | `slave=1` |
| **Expected result** | Unit ID matches config |

**Steps:**

1. Sniff Modbus frame unit id

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-164 — FC5 50 consecutive IDLE↔GRANT cycles

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-164` |
| **Module / Category** | Modbus FC5 / Stress |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5 DEMO or live |
| **Test data** | `50 cycles` |
| **Expected result** | Stable; coils correct at end |

**Steps:**

1. Automate 50 grant/reset cycles
2. Check final coils + no crash

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-165 — FC5 write under SENSOR_POLL concurrent DI reads

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-165` |
| **Module / Category** | Modbus FC5 / Stress |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; poll 0.3s |
| **Test data** | `concurrent` |
| **Expected result** | No Modbus frame corruption; app thread-safe |

**Steps:**

1. Grant while DI polling active

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-166 — modbus_tcp_app.py FC5 mode matches runtime

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-166` |
| **Module / Category** | Modbus FC5 / Tool |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | tests/modbus_tcp_app.py |
| **Test data** | `FC5` |
| **Expected result** | Tool and app agree on coil effects |

**Steps:**

1. Run tool write_fc=5
2. Toggle same pins as app

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-167 — JSON digital_outputs.function_code=5 selected

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-167` |
| **Module / Category** | Modbus FC5 / Config |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | iot_configuration |
| **Test data** | `"function_code":"5"` |
| **Expected result** | Startup log write_fc=5 |

**Steps:**

1. Set function_code 5
2. Restart
3. Log write_fc

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-168 — function_codes.write_single_coil catalog present

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-168` |
| **Module / Category** | Modbus FC5 / Config |
| **Priority / Type** | P3 / Positive |
| **Preconditions** | JSON function_codes block |
| **Test data** | `write_single_coil=5` |
| **Expected result** | Catalog documents FC5 |

**Steps:**

1. Open iot_configuration
2. Confirm write_single_coil=5

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-169 — Field acceptance: operator confirms Traffic light RED physical response (FC5)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-169` |
| **Module / Category** | Modbus FC5 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live site; write_fc=5; safe area |
| **Test data** | `DO0 / entry_tl_red` |
| **Expected result** | Physical Traffic light RED matches command |

**Steps:**

1. From dashboard/reset/grant assert Traffic light RED
2. Operator visually confirms lamp/boom
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-170 — Field acceptance: operator confirms Traffic light GREEN physical response (FC5)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-170` |
| **Module / Category** | Modbus FC5 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live site; write_fc=5; safe area |
| **Test data** | `DO1 / entry_tl_green` |
| **Expected result** | Physical Traffic light GREEN matches command |

**Steps:**

1. From dashboard/reset/grant assert Traffic light GREEN
2. Operator visually confirms lamp/boom
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-171 — Field acceptance: operator confirms Boom OPEN physical response (FC5)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-171` |
| **Module / Category** | Modbus FC5 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live site; write_fc=5; safe area |
| **Test data** | `DO2 / entry_boom_open` |
| **Expected result** | Physical Boom OPEN matches command |

**Steps:**

1. From dashboard/reset/grant assert Boom OPEN
2. Operator visually confirms lamp/boom
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-172 — Field acceptance: operator confirms Boom CLOSE physical response (FC5)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-172` |
| **Module / Category** | Modbus FC5 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live site; write_fc=5; safe area |
| **Test data** | `DO3 / entry_boom_close` |
| **Expected result** | Physical Boom CLOSE matches command |

**Steps:**

1. From dashboard/reset/grant assert Boom CLOSE
2. Operator visually confirms lamp/boom
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-173 — Unused DO4 not written during mines_entry cycle

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-173` |
| **Module / Category** | Modbus FC5 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=5; map only 0-3 |
| **Test data** | `DO4` |
| **Expected result** | No unexpected FC5 writes to 4 |

**Steps:**

1. Full happy path
2. Sniff Modbus
3. Confirm no FC5 to addr 4

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-174 — Unused DO5 not written during mines_entry cycle

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-174` |
| **Module / Category** | Modbus FC5 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=5; map only 0-3 |
| **Test data** | `DO5` |
| **Expected result** | No unexpected FC5 writes to 5 |

**Steps:**

1. Full happy path
2. Sniff Modbus
3. Confirm no FC5 to addr 5

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-175 — Unused DO6 not written during mines_entry cycle

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-175` |
| **Module / Category** | Modbus FC5 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=5; map only 0-3 |
| **Test data** | `DO6` |
| **Expected result** | No unexpected FC5 writes to 6 |

**Steps:**

1. Full happy path
2. Sniff Modbus
3. Confirm no FC5 to addr 6

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-176 — Unused DO7 not written during mines_entry cycle

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-176` |
| **Module / Category** | Modbus FC5 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=5; map only 0-3 |
| **Test data** | `DO7` |
| **Expected result** | No unexpected FC5 writes to 7 |

**Steps:**

1. Full happy path
2. Sniff Modbus
3. Confirm no FC5 to addr 7

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Modbus FC6

### TC-ME-177 — Switch digital_outputs.function_code to 6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-177` |
| **Module / Category** | Modbus FC6 / Config |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Controller supports holding register writes |
| **Test data** | `"function_code":"6"` |
| **Expected result** | Startup log write_fc=6 |

**Steps:**

1. Set function_code=6
2. Restart
3. Check log write_fc=6

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-178 — function_codes.write_single_register catalog = 6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-178` |
| **Module / Category** | Modbus FC6 / Config |
| **Priority / Type** | P3 / Positive |
| **Preconditions** | JSON |
| **Test data** | `6` |
| **Expected result** | Documented |

**Steps:**

1. Confirm write_single_register=6 in catalog

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-179 — FC6 write register=1 for entry_tl_red (DO0)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-179` |
| **Module / Category** | Modbus FC6 / Write 1 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6; controller maps 1=ON |
| **Test data** | `FC6 addr=0 value=1` |
| **Expected result** | Register 0=1; Traffic light RED ON |

**Steps:**

1. Assert Traffic light RED
2. Capture FC6 addr 0 value 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-180 — FC6 write register=0 for entry_tl_red (DO0)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-180` |
| **Module / Category** | Modbus FC6 / Write 0 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `FC6 addr=0 value=0` |
| **Expected result** | Register 0=0; Traffic light RED OFF |

**Steps:**

1. De-assert Traffic light RED
2. Capture FC6 value 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-181 — FC6 entry_tl_red verified via FC3 read holding

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-181` |
| **Module / Category** | Modbus FC6 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; external FC3 |
| **Test data** | `DO0` |
| **Expected result** | Holding register matches 0/1 |

**Steps:**

1. App writes
2. FC3 read register 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-182 — FC6 write failure to entry_tl_red

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-182` |
| **Module / Category** | Modbus FC6 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Break FC6 path |
| **Test data** | `DO0` |
| **Expected result** | Error logged; safe behavior |

**Steps:**

1. Force exception
2. Trigger Traffic light RED

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-183 — Field acceptance: Traffic light RED physical response under FC6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-183` |
| **Module / Category** | Modbus FC6 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live; write_fc=6 |
| **Test data** | `entry_tl_red` |
| **Expected result** | Physical match under register mode |

**Steps:**

1. Command Traffic light RED
2. Visual confirm
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-184 — FC6 write register=1 for entry_tl_green (DO1)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-184` |
| **Module / Category** | Modbus FC6 / Write 1 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6; controller maps 1=ON |
| **Test data** | `FC6 addr=1 value=1` |
| **Expected result** | Register 1=1; Traffic light GREEN ON |

**Steps:**

1. Assert Traffic light GREEN
2. Capture FC6 addr 1 value 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-185 — FC6 write register=0 for entry_tl_green (DO1)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-185` |
| **Module / Category** | Modbus FC6 / Write 0 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `FC6 addr=1 value=0` |
| **Expected result** | Register 1=0; Traffic light GREEN OFF |

**Steps:**

1. De-assert Traffic light GREEN
2. Capture FC6 value 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-186 — FC6 entry_tl_green verified via FC3 read holding

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-186` |
| **Module / Category** | Modbus FC6 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; external FC3 |
| **Test data** | `DO1` |
| **Expected result** | Holding register matches 0/1 |

**Steps:**

1. App writes
2. FC3 read register 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-187 — FC6 write failure to entry_tl_green

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-187` |
| **Module / Category** | Modbus FC6 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Break FC6 path |
| **Test data** | `DO1` |
| **Expected result** | Error logged; safe behavior |

**Steps:**

1. Force exception
2. Trigger Traffic light GREEN

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-188 — Field acceptance: Traffic light GREEN physical response under FC6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-188` |
| **Module / Category** | Modbus FC6 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live; write_fc=6 |
| **Test data** | `entry_tl_green` |
| **Expected result** | Physical match under register mode |

**Steps:**

1. Command Traffic light GREEN
2. Visual confirm
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-189 — FC6 write register=1 for entry_boom_open (DO2)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-189` |
| **Module / Category** | Modbus FC6 / Write 1 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6; controller maps 1=ON |
| **Test data** | `FC6 addr=2 value=1` |
| **Expected result** | Register 2=1; Boom OPEN ON |

**Steps:**

1. Assert Boom OPEN
2. Capture FC6 addr 2 value 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-190 — FC6 write register=0 for entry_boom_open (DO2)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-190` |
| **Module / Category** | Modbus FC6 / Write 0 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `FC6 addr=2 value=0` |
| **Expected result** | Register 2=0; Boom OPEN OFF |

**Steps:**

1. De-assert Boom OPEN
2. Capture FC6 value 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-191 — FC6 entry_boom_open verified via FC3 read holding

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-191` |
| **Module / Category** | Modbus FC6 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; external FC3 |
| **Test data** | `DO2` |
| **Expected result** | Holding register matches 0/1 |

**Steps:**

1. App writes
2. FC3 read register 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-192 — FC6 write failure to entry_boom_open

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-192` |
| **Module / Category** | Modbus FC6 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Break FC6 path |
| **Test data** | `DO2` |
| **Expected result** | Error logged; safe behavior |

**Steps:**

1. Force exception
2. Trigger Boom OPEN

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-193 — Field acceptance: Boom OPEN physical response under FC6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-193` |
| **Module / Category** | Modbus FC6 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live; write_fc=6 |
| **Test data** | `entry_boom_open` |
| **Expected result** | Physical match under register mode |

**Steps:**

1. Command Boom OPEN
2. Visual confirm
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-194 — FC6 write register=1 for entry_boom_close (DO3)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-194` |
| **Module / Category** | Modbus FC6 / Write 1 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6; controller maps 1=ON |
| **Test data** | `FC6 addr=3 value=1` |
| **Expected result** | Register 3=1; Boom CLOSE ON |

**Steps:**

1. Assert Boom CLOSE
2. Capture FC6 addr 3 value 1

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-195 — FC6 write register=0 for entry_boom_close (DO3)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-195` |
| **Module / Category** | Modbus FC6 / Write 0 |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `FC6 addr=3 value=0` |
| **Expected result** | Register 3=0; Boom CLOSE OFF |

**Steps:**

1. De-assert Boom CLOSE
2. Capture FC6 value 0

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-196 — FC6 entry_boom_close verified via FC3 read holding

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-196` |
| **Module / Category** | Modbus FC6 / Verify |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; external FC3 |
| **Test data** | `DO3` |
| **Expected result** | Holding register matches 0/1 |

**Steps:**

1. App writes
2. FC3 read register 3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-197 — FC6 write failure to entry_boom_close

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-197` |
| **Module / Category** | Modbus FC6 / Failure |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Break FC6 path |
| **Test data** | `DO3` |
| **Expected result** | Error logged; safe behavior |

**Steps:**

1. Force exception
2. Trigger Boom CLOSE

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-198 — Field acceptance: Boom CLOSE physical response under FC6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-198` |
| **Module / Category** | Modbus FC6 / Field |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live; write_fc=6 |
| **Test data** | `entry_boom_close` |
| **Expected result** | Physical match under register mode |

**Steps:**

1. Command Boom CLOSE
2. Visual confirm
3. Sign off

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-199 — FC6 IDLE register pattern 1,0,0,1 on DO0-3

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-199` |
| **Module / Category** | Modbus FC6 / Sequence |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6; IDLE |
| **Test data** | `1,0,0,1` |
| **Expected result** | Matches idle red/close |

**Steps:**

1. Reset IDLE
2. FC3 read 0-3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-200 — FC6 GRANT register pattern 0,1,1,0

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-200` |
| **Module / Category** | Modbus FC6 / Sequence |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6; grant |
| **Test data** | `0,1,1,0` |
| **Expected result** | Green + open |

**Steps:**

1. Grant
2. FC3 read 0-3

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-201 — FC6 after clear returns idle registers

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-201` |
| **Module / Category** | Modbus FC6 / Sequence |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `idle pattern` |
| **Expected result** | Safe idle |

**Steps:**

1. Complete clear+delay
2. Read registers

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-202 — Same workflow FC5 vs FC6 produces same field result

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-202` |
| **Module / Category** | Modbus FC6 / Compare |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Controller supports both (or two benches) |
| **Test data** | `FC5 then FC6` |
| **Expected result** | Operator-visible behavior identical |

**Steps:**

1. Run happy path FC5
2. Switch FC6
3. Repeat
4. Compare TL/boom behavior

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-203 — Wireshark: FC5 PDU vs FC6 PDU differ

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-203` |
| **Module / Category** | Modbus FC6 / Compare |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Packet capture |
| **Test data** | `0x05 vs 0x06` |
| **Expected result** | Frames show correct function codes |

**Steps:**

1. Capture one TL write under FC5
2. Capture under FC6
3. Compare function code byte

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-204 — FC6 against coil-only device fails safely

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-204` |
| **Module / Category** | Modbus FC6 / Negative |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Device rejects FC6 |
| **Test data** | `exception` |
| **Expected result** | Writes fail; boom not falsely reported open |

**Steps:**

1. Set write_fc=6 on coil-only PLC
2. Start grant

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-205 — FC5 against register-only device fails safely

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-205` |
| **Module / Category** | Modbus FC6 / Negative |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Device rejects FC5 |
| **Test data** | `exception` |
| **Expected result** | Safe fail; logged |

**Steps:**

1. write_fc=5 on register PLC
2. Grant

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-206 — FC6 maps bool True→1 False→0 only

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-206` |
| **Module / Category** | Modbus FC6 / Value |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6 code path |
| **Test data** | `0 or 1` |
| **Expected result** | Never writes 2/65535 accidentally |

**Steps:**

1. Inspect gmdc_common write_coil FC6 branch
2. Confirm no other values written

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-207 — FC6 50 IDLE↔GRANT cycles

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-207` |
| **Module / Category** | Modbus FC6 / Stress |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `50` |
| **Expected result** | Stable idle registers |

**Steps:**

1. 50 cycles
2. Final register read

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-208 — FC6 concurrent with FC2 DI polling

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-208` |
| **Module / Category** | Modbus FC6 / Stress |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `concurrent` |
| **Expected result** | No deadlock / corruption |

**Steps:**

1. Grant under active DI poll

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-209 — modbus_tcp_app.py choose write FC6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-209` |
| **Module / Category** | Modbus FC6 / Tool |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | tests/modbus_tcp_app.py |
| **Test data** | `FC6` |
| **Expected result** | Registers change; matches app |

**Steps:**

1. Run tool with write_fc=6
2. Toggle outputs

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-210 — Hot config change FC5→FC6 requires restart

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-210` |
| **Module / Category** | Modbus FC6 / Switch |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | Running app |
| **Test data** | `restart needed` |
| **Expected result** | Documents restart requirement |

**Steps:**

1. Edit JSON to 6 without restart
2. Observe still FC5 until restart

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-211 — After restart FC6 takes effect

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-211` |
| **Module / Category** | Modbus FC6 / Switch |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | JSON=6 |
| **Test data** | `write_fc=6` |
| **Expected result** | New writes use FC6 |

**Steps:**

1. Restart
2. Capture write

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-212 — Unused register DO4 not written (FC6)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-212` |
| **Module / Category** | Modbus FC6 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `DO4` |
| **Expected result** | No stray writes |

**Steps:**

1. Happy path
2. Confirm no FC6 to 4

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-213 — Unused register DO5 not written (FC6)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-213` |
| **Module / Category** | Modbus FC6 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `DO5` |
| **Expected result** | No stray writes |

**Steps:**

1. Happy path
2. Confirm no FC6 to 5

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-214 — Unused register DO6 not written (FC6)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-214` |
| **Module / Category** | Modbus FC6 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `DO6` |
| **Expected result** | No stray writes |

**Steps:**

1. Happy path
2. Confirm no FC6 to 6

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-215 — Unused register DO7 not written (FC6)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-215` |
| **Module / Category** | Modbus FC6 / Unused |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `DO7` |
| **Expected result** | No stray writes |

**Steps:**

1. Happy path
2. Confirm no FC6 to 7

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Modbus Mixed

### TC-ME-216 — Always read DI with FC2 regardless of write FC5

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-216` |
| **Module / Category** | Modbus Mixed / RW |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=5 |
| **Test data** | `FC2+FC5` |
| **Expected result** | Read FC2 write FC5 |

**Steps:**

1. Poll sensor
2. Confirm FC2 reads

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-217 — Always read DI with FC2 regardless of write FC6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-217` |
| **Module / Category** | Modbus Mixed / RW |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `FC2+FC6` |
| **Expected result** | Read FC2 write FC6 |

**Steps:**

1. Poll sensor
2. Confirm FC2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-218 — JSON lists FC1,2,3,4,5,6,15,16 for documentation

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-218` |
| **Module / Category** | Modbus Mixed / Catalog |
| **Priority / Type** | P3 / Positive |
| **Preconditions** | iot_configuration function_codes |
| **Test data** | `1/2/3/4/5/6/15/16` |
| **Expected result** | Catalog complete for auditors |

**Steps:**

1. Open JSON
2. Verify catalog keys

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## E2E

### TC-ME-219 — Full happy path reader RFID → ANPR1 → grant → clear → IDLE (FC5)

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-219` |
| **Module / Category** | E2E / Happy |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Live stack write_fc=5 |
| **Test data** | `valid tag` |
| **Expected result** | End IDLE; TL red; boom closed; FC5 coils idle |

**Steps:**

1. POST /rfid_data
2. OCI 200
3. ANPR 1
4. boom-close 200
5. Sensor TRUE→FALSE
6. Wait boom delay

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-220 — Full happy path same on FC6 write mode

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-220` |
| **Module / Category** | E2E / Happy |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | write_fc=6 |
| **Test data** | `FC6` |
| **Expected result** | Same functional end state |

**Steps:**

Same steps as previous

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-221 — Mobile RFID happy path to IDLE

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-221` |
| **Module / Category** | E2E / Happy |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Mobile + stack up |
| **Test data** | `mobile` |
| **Expected result** | IDLE end; mobile got OCI JSON |

**Steps:**

1. POST mobile rfid
2. Complete grant+clear

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-222 — ANPR0 → status_check1 → grant → clear

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-222` |
| **Module / Category** | E2E / Manual |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | ANPR on |
| **Test data** | `0 then 1` |
| **Expected result** | Grant after manual; IDLE after clear |

**Steps:**

1. ANPR 0
2. status_check 1
3. Clear sensor

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-223 — ANPR2 → status_check1 → grant → clear

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-223` |
| **Module / Category** | E2E / Manual |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | ANPR on |
| **Test data** | `2 then 1` |
| **Expected result** | Grant after manual |

**Steps:**

1. ANPR 2
2. status_check 1
3. Clear

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-224 — ANPR disabled → invalid-truck2 → status_check1 → grant

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-224` |
| **Module / Category** | E2E / Manual |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | anpr_enabled=false |
| **Test data** | `anpr off` |
| **Expected result** | No detect; status_check used; grant works |

**Steps:**

1. RFID valid
2. Approve status_check
3. Clear

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-225 — RFID invalid full cycle

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-225` |
| **Module / Category** | E2E / Reject |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | IDLE |
| **Test data** | `OCI fail` |
| **Expected result** | RFID ERR 1 → IDLE; boom never opened |

**Steps:**

1. Bad RFID
2. Wait display timer

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-226 — Manual vehicleStatus=2 abort

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-226` |
| **Module / Category** | E2E / Reject |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | MANUAL |
| **Test data** | `vehicleStatus=2` |
| **Expected result** | IDLE; boom closed |

**Steps:**

1. status_check returns 2

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-227 — boom-close fail prevents open

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-227` |
| **Module / Category** | E2E / Reject |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | ANPR1 |
| **Test data** | `500` |
| **Expected result** | No open; safe |

**Steps:**

1. boom-close 500

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Robustness

### TC-ME-228 — Second RFID ignored while busy

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-228` |
| **Module / Category** | Robustness / Concurrency |
| **Priority / Type** | P0 / Negative |
| **Preconditions** | First cycle running |
| **Test data** | `two tags` |
| **Expected result** | Second ignored |

**Steps:**

1. Start cycle
2. Immediate second RFID

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-229 — Kill process mid WAIT_CROSSING then restart

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-229` |
| **Module / Category** | Robustness / Restart |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Live |
| **Test data** | `kill` |
| **Expected result** | Restarts IDLE safe hardware |

**Steps:**

1. Grant
2. Kill app
3. Restart

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-230 — OCI flaky network mid status_check

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-230` |
| **Module / Category** | Robustness / Network |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | MANUAL |
| **Test data** | `flaky` |
| **Expected result** | Recovers or alerts; no false grant |

**Steps:**

1. Drop packets intermittently

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-231 — System clock jump during timers

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-231` |
| **Module / Category** | Robustness / Clock |
| **Priority / Type** | P3 / Negative |
| **Preconditions** | Test VM |
| **Test data** | `time jump` |
| **Expected result** | No crash; document timer behavior |

**Steps:**

1. Change clock ±1h during wait

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-232 — 8-hour soak IDLE with DI polling

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-232` |
| **Module / Category** | Robustness / Long run |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc site default |
| **Test data** | `8h` |
| **Expected result** | No leak crash; still accepts RFID |

**Steps:**

1. Leave overnight IDLE
2. Check memory/logs

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-233 — 100 trucks simulated happy path

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-233` |
| **Module / Category** | Robustness / Long run |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | DEMO or staging |
| **Test data** | `100` |
| **Expected result** | All complete or failures counted |

**Steps:**

1. Script 100 cycles

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Security

### TC-ME-234 — .env not committed / not in bundle logs

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-234` |
| **Module / Category** | Security / Secrets |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Repo + package |
| **Test data** | `.env` |
| **Expected result** | No password echo in normal logs |

**Steps:**

1. Check gitignore
2. Check logs for passwords

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-235 — Operator endpoints require login where designed

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-235` |
| **Module / Category** | Security / Auth |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Logged out |
| **Test data** | `no session` |
| **Expected result** | Blocked |

**Steps:**

1. Try free pass/reset UI

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Packaging

### TC-ME-236 — Frozen mines-checkpoint serves static/web

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-236` |
| **Module / Category** | Packaging / macOS |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | Mines-Automation bundle |
| **Test data** | `frozen` |
| **Expected result** | Dashboard loads |

**Steps:**

1. Run mines-checkpoint
2. Open web UI

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-237 — automation launches mines-checkpoint for mines_entry

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-237` |
| **Module / Category** | Packaging / macOS |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | iot_configuration checkpoint_type=mines_entry |
| **Test data** | `mines_entry` |
| **Expected result** | Selects mines-checkpoint |

**Steps:**

1. Run ./automation --dry-run

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-238 — App runs without internet after install

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-238` |
| **Module / Category** | Packaging / Offline |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Offline LAN only |
| **Test data** | `no WAN` |
| **Expected result** | No pip download; local deps only |

**Steps:**

1. Disconnect WAN
2. Run cycle to local OCI/ANPR if any

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## MQTT

### TC-ME-239 — Mosquitto 1883/9001 up before app

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-239` |
| **Module / Category** | MQTT / Broker |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | Local Mosquitto |
| **Test data** | `1883/9001` |
| **Expected result** | Frontend MQTT connects |

**Steps:**

1. Ensure ports
2. Start app

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-240 — Broker down: app still processes RFID/OCI

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-240` |
| **Module / Category** | MQTT / Broker |
| **Priority / Type** | P1 / Negative |
| **Preconditions** | Stop Mosquitto |
| **Test data** | `broker down` |
| **Expected result** | Core workflow works; display may fallback |

**Steps:**

1. Start app
2. RFID cycle

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## Matrix

### TC-ME-241 — End-to-end ANPR0 with write_fc=5

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-241` |
| **Module / Category** | Matrix / FC5+ANPR0 |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; ANPR returns 0 |
| **Test data** | `FC5 + status 0` |
| **Expected result** | Hardware commands use configured write FC; workflow matches status rules |

**Steps:**

1. Set write_fc=5
2. Force anpr_status=0
3. Complete resulting path (grant or status_check)
4. Verify TL/boom via Modbus

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-242 — End-to-end ANPR1 with write_fc=5

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-242` |
| **Module / Category** | Matrix / FC5+ANPR1 |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; ANPR returns 1 |
| **Test data** | `FC5 + status 1` |
| **Expected result** | Hardware commands use configured write FC; workflow matches status rules |

**Steps:**

1. Set write_fc=5
2. Force anpr_status=1
3. Complete resulting path (grant or status_check)
4. Verify TL/boom via Modbus

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-243 — End-to-end ANPR2 with write_fc=5

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-243` |
| **Module / Category** | Matrix / FC5+ANPR2 |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=5; ANPR returns 2 |
| **Test data** | `FC5 + status 2` |
| **Expected result** | Hardware commands use configured write FC; workflow matches status rules |

**Steps:**

1. Set write_fc=5
2. Force anpr_status=2
3. Complete resulting path (grant or status_check)
4. Verify TL/boom via Modbus

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-244 — End-to-end ANPR0 with write_fc=6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-244` |
| **Module / Category** | Matrix / FC6+ANPR0 |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; ANPR returns 0 |
| **Test data** | `FC6 + status 0` |
| **Expected result** | Hardware commands use configured write FC; workflow matches status rules |

**Steps:**

1. Set write_fc=6
2. Force anpr_status=0
3. Complete resulting path (grant or status_check)
4. Verify TL/boom via Modbus

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-245 — End-to-end ANPR1 with write_fc=6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-245` |
| **Module / Category** | Matrix / FC6+ANPR1 |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; ANPR returns 1 |
| **Test data** | `FC6 + status 1` |
| **Expected result** | Hardware commands use configured write FC; workflow matches status rules |

**Steps:**

1. Set write_fc=6
2. Force anpr_status=1
3. Complete resulting path (grant or status_check)
4. Verify TL/boom via Modbus

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-246 — End-to-end ANPR2 with write_fc=6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-246` |
| **Module / Category** | Matrix / FC6+ANPR2 |
| **Priority / Type** | P1 / Positive |
| **Preconditions** | write_fc=6; ANPR returns 2 |
| **Test data** | `FC6 + status 2` |
| **Expected result** | Hardware commands use configured write FC; workflow matches status rules |

**Steps:**

1. Set write_fc=6
2. Force anpr_status=2
3. Complete resulting path (grant or status_check)
4. Verify TL/boom via Modbus

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-247 — BOOM_CLOSE_DELAY under write_fc=5

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-247` |
| **Module / Category** | Matrix / Boom delay |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=5; delay=10 |
| **Test data** | `FC5` |
| **Expected result** | ~10s then close asserted |

**Steps:**

1. Grant
2. Clear sensor
3. Measure time to close coil/register

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-248 — BOOM_CLOSE_DELAY under write_fc=6

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-248` |
| **Module / Category** | Matrix / Boom delay |
| **Priority / Type** | P2 / Positive |
| **Preconditions** | write_fc=6; delay=10 |
| **Test data** | `FC6` |
| **Expected result** | ~10s then close asserted |

**Steps:**

1. Grant
2. Clear sensor
3. Measure time to close coil/register

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

## UAT

### TC-ME-249 — UAT sign-off: App starts without error dialog

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-249` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: App starts without error dialog |

**Steps:**

1. Perform scenario for: App starts without error dialog
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-250 — UAT sign-off: Dashboard opens in browser

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-250` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Dashboard opens in browser |

**Steps:**

1. Perform scenario for: Dashboard opens in browser
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-251 — UAT sign-off: IDLE shows red light

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-251` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: IDLE shows red light |

**Steps:**

1. Perform scenario for: IDLE shows red light
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-252 — UAT sign-off: IDLE boom is down/closed

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-252` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: IDLE boom is down/closed |

**Steps:**

1. Perform scenario for: IDLE boom is down/closed
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-253 — UAT sign-off: Valid tag starts cycle

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-253` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Valid tag starts cycle |

**Steps:**

1. Perform scenario for: Valid tag starts cycle
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-254 — UAT sign-off: Truck number appears on display

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-254` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Truck number appears on display |

**Steps:**

1. Perform scenario for: Truck number appears on display
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-255 — UAT sign-off: Green light on grant

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-255` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Green light on grant |

**Steps:**

1. Perform scenario for: Green light on grant
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-256 — UAT sign-off: Boom raises on grant

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-256` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Boom raises on grant |

**Steps:**

1. Perform scenario for: Boom raises on grant
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-257 — UAT sign-off: Truck on sensor detected

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-257` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Truck on sensor detected |

**Steps:**

1. Perform scenario for: Truck on sensor detected
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-258 — UAT sign-off: After truck leaves boom lowers

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-258` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: After truck leaves boom lowers |

**Steps:**

1. Perform scenario for: After truck leaves boom lowers
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-259 — UAT sign-off: Light returns to red

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-259` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Light returns to red |

**Steps:**

1. Perform scenario for: Light returns to red
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-260 — UAT sign-off: Invalid tag shows error on display

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-260` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Invalid tag shows error on display |

**Steps:**

1. Perform scenario for: Invalid tag shows error on display
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-261 — UAT sign-off: ANPR mismatch waits for office approval

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-261` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: ANPR mismatch waits for office approval |

**Steps:**

1. Perform scenario for: ANPR mismatch waits for office approval
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-262 — UAT sign-off: Office approval then boom opens

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-262` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Office approval then boom opens |

**Steps:**

1. Perform scenario for: Office approval then boom opens
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-263 — UAT sign-off: Reset button returns to idle safely

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-263` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Reset button returns to idle safely |

**Steps:**

1. Perform scenario for: Reset button returns to idle safely
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-264 — UAT sign-off: Free pass only after login

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-264` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Free pass only after login |

**Steps:**

1. Perform scenario for: Free pass only after login
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-265 — UAT sign-off: ANPR toggle off still waits status_check

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-265` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: ANPR toggle off still waits status_check |

**Steps:**

1. Perform scenario for: ANPR toggle off still waits status_check
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-266 — UAT sign-off: No boom open if server boom-close fails

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-266` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: No boom open if server boom-close fails |

**Steps:**

1. Perform scenario for: No boom open if server boom-close fails
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-267 — UAT sign-off: Demo mode works without PLC

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-267` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Demo mode works without PLC |

**Steps:**

1. Perform scenario for: Demo mode works without PLC
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-268 — UAT sign-off: Live mode talks to PLC

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-268` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Live mode talks to PLC |

**Steps:**

1. Perform scenario for: Live mode talks to PLC
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-269 — UAT sign-off: FC5 site coils correct

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-269` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: FC5 site coils correct |

**Steps:**

1. Perform scenario for: FC5 site coils correct
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-270 — UAT sign-off: FC6 site registers correct

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-270` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: FC6 site registers correct |

**Steps:**

1. Perform scenario for: FC6 site registers correct
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-271 — UAT sign-off: Mosquitto running

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-271` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Mosquitto running |

**Steps:**

1. Perform scenario for: Mosquitto running
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-272 — UAT sign-off: Logs written under logs/

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-272` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Logs written under logs/ |

**Steps:**

1. Perform scenario for: Logs written under logs/
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

### TC-ME-273 — UAT sign-off: Restart after power cut is safe

| Field | Detail |
|-------|--------|
| **ID** | `TC-ME-273` |
| **Module / Category** | UAT / Sign-off |
| **Priority / Type** | P0 / Positive |
| **Preconditions** | mines_entry site ready; stakeholders present |
| **Test data** | `UAT` |
| **Expected result** | Signed Pass for: Restart after power cut is safe |

**Steps:**

1. Perform scenario for: Restart after power cut is safe
2. Stakeholder initials
3. Pass/Fail

| Result | Tester | Date | Evidence |
|--------|--------|------|----------|
| ☐ Pass ☐ Fail ☐ Blocked |  |  |  |

---

**End of catalogue — 273 test cases for Mines Entry (`mines_entry`).**
