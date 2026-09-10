"""Generate docs/Mines_Entry_Test_Cases.csv for Tracking Point QA."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "Mines_Entry_Test_Cases.csv"

HEADERS = [
    "TC_ID",
    "Module",
    "Category",
    "Title",
    "Preconditions",
    "Steps",
    "Test_Data",
    "Expected_Result",
    "Priority",
    "Type",
]

ROWS = [
    # Health / Status
    ["TC-API-001", "API", "Health", "Root health check", "App running on port 8080", "1. GET /", "None", "HTTP 200; JSON service=GMDC Tracking Point status=running", "P1", "Positive"],
    ["TC-API-002", "API", "Status", "Get application status while IDLE", "App in IDLE state", "1. GET /api/status", "None", "HTTP 200; state=IDLE; hardware and transaction snapshot present", "P1", "Positive"],
    ["TC-API-003", "API", "Reset", "Force reset to IDLE", "App in any state", "1. POST /api/reset", "None", "HTTP 200; message Application reset to IDLE; TL red boom closed; RFID IDLE prepare", "P1", "Positive"],
    ["TC-API-004", "API", "Simulate", "Simulate entry sensor clear (demo)", "demo_mode=true OR DemoIO; state WAIT_CROSSING", "1. POST /api/simulate-exit", "None", "HTTP 200; sensor pulse TRUE then FALSE; boom closed TL red; state IDLE", "P2", "Positive"],
    # RFID reader HTTP
    ["TC-RFID-001", "RFID", "Reader API", "Accept valid Zebra tag payload on /rfid_data", "State IDLE; OCI RFID available", "1. POST /rfid_data with Zebra tag list", '[{"data":{"idHex":"E200001D7507013115006BB9"},"type":"TAG"}]', "HTTP 200 status=success; tags returned; workflow starts; RFID cloud stop called", "P0", "Positive"],
    ["TC-RFID-002", "RFID", "Reader API", "Reject empty tag list on /rfid_data", "State IDLE", "1. POST /rfid_data with []", "[]", "HTTP 400; No idHex tags found", "P1", "Negative"],
    ["TC-RFID-003", "RFID", "Reader API", "Reject invalid JSON on /rfid_data", "State IDLE", "1. POST /rfid_data with non-JSON body", "not-json", "HTTP 400 error message", "P2", "Negative"],
    ["TC-RFID-004", "RFID", "Reader API", "Ignore RFID while not IDLE", "State WAIT_CROSSING or MANUAL_UPDATE", "1. POST /rfid_data with valid tags", "Valid idHex payload", "Tags ignored; log Ignoring RFID tags while in state", "P1", "Negative"],
    ["TC-RFID-005", "RFID", "Management", "RFID management keepalive", "App running", "1. POST /rfid_management", "{}", "HTTP 200 status=success", "P2", "Positive"],
    ["TC-RFID-006", "RFID", "Alias", "Accept tags via /api/read-rfid alias", "State IDLE", "1. POST /api/read-rfid with valid tags", "Same as TC-RFID-001", "HTTP 200; workflow accepts tags", "P2", "Positive"],
    ["TC-RFID-007", "RFID", "Alias", "Accept tags via /read_rfid alias", "State IDLE", "1. POST /read_rfid with valid tags", "Same as TC-RFID-001", "HTTP 200; workflow accepts tags", "P3", "Positive"],
    # Mobile RFID
    ["TC-MOB-001", "Mobile RFID", "API", "Mobile RFID returns OCI validate body HTTP 200", "State IDLE; OCI reachable", "1. POST /rfid_data_from_mobile_app", '{"rfid_data":"1234567890"}', "HTTP 200; body equals OCI rfid-validate response", "P0", "Positive"],
    ["TC-MOB-002", "Mobile RFID", "API", "Mobile RFID missing key", "State IDLE", "1. POST without rfid_data", "{}", "HTTP 500; status=500; rfid_data=null; message starts with Error:", "P1", "Negative"],
    ["TC-MOB-003", "Mobile RFID", "API", "Mobile RFID blank value", "State IDLE", "1. POST blank rfid_data", '{"rfid_data":"   "}', "HTTP 500; rfid_data=null; Error: rfid_data value is blank", "P1", "Negative"],
    ["TC-MOB-004", "Mobile RFID", "API", "Mobile RFID null value", "State IDLE", "1. POST null rfid_data", '{"rfid_data":null}', "HTTP 500; rfid_data=null", "P2", "Negative"],
    ["TC-MOB-005", "Mobile RFID", "Workflow", "Valid mobile RFID continues to ANPR like reader", "State IDLE; OCI RFID returns 200", "1. POST valid mobile RFID 2. Observe ANPR", "Valid rfid + OCI 200", "OCI body returned; background ANPR then grant/manual", "P0", "Positive"],
    ["TC-MOB-006", "Mobile RFID", "Workflow", "Invalid mobile RFID shows RFID ERR 1 then IDLE", "State IDLE; OCI RFID status 500", "1. POST unknown rfid", '{"rfid_data":"BADTAG"}', "HTTP 200 with OCI error body; display RFID ERR 1; wait ~10s; IDLE", "P0", "Positive"],
    ["TC-MOB-007", "Mobile RFID", "Busy", "Mobile RFID while workflow busy", "Another cycle in progress", "1. POST /rfid_data_from_mobile_app", '{"rfid_data":"1234567890"}', "HTTP 500 Error: Workflow busy or Ignoring RFID while in state", "P1", "Negative"],
    # OCI RFID
    ["TC-OCI-001", "OCI", "RFID Validate", "RFID validate success parses truck_details", "Valid tag", "1. Trigger RFID cycle with valid tag", "truck_details pipe string", "vehicle_no token_no set; display truck; proceed ANPR", "P0", "Positive"],
    ["TC-OCI-002", "OCI", "RFID Validate", "RFID validate failure path", "Invalid RFID", "1. Trigger RFID with bad tag", "OCI {status:500}", "Display RFID ERR 1; wait 10s; IDLE; boom closed TL red", "P0", "Positive"],
    ["TC-OCI-003", "OCI", "RFID Validate", "RFID validate payload fields", "Any RFID cycle", "1. Capture OCI request", "rfid + device_ip", "Request body contains rfid and device_ip", "P1", "Positive"],
    # ANPR
    ["TC-ANPR-001", "ANPR", "Detect", "anpr_status=1 grants entry", "RFID valid", "1. ANPR returns anpr_status=1 2. Observe hardware", '{"anpr_status":1}', "invalid-truck posted; boom-close; if 200 boom OPEN TL GREEN; Entry Granted; WAIT_CROSSING", "P0", "Positive"],
    ["TC-ANPR-002", "ANPR", "Detect", "anpr_status=0 shows ANPR ERR 1 and manual loop", "RFID valid", "1. ANPR returns anpr_status=0", '{"anpr_status":0}', "invalid-truck posted; display ANPR ERR 1; poll status_check", "P0", "Positive"],
    ["TC-ANPR-003", "ANPR", "Detect", "anpr_status=2 shows ANPR Err-2 then reset", "RFID valid", "1. ANPR returns anpr_status=2", '{"anpr_status":2}', "invalid-truck posted; display ANPR Err-2; wait ANPR_ERR_2_DISPLAY_SEC; IDLE", "P0", "Positive"],
    ["TC-ANPR-004", "ANPR", "Retry", "ANPR API exception retries 3 times then ANPR API ERR", "RFID valid; ANPR down", "1. Force ConnectionError on detect", "ANPR unreachable", "3 attempts ~2s delay; ANPR API ERR; IDLE; boom not opened", "P0", "Positive"],
    ["TC-ANPR-005", "ANPR", "Retry", "ANPR succeeds on second retry", "RFID valid; first detect fails", "1. First fail 2. Second status 1", "fail then success", "Grant entry after 2 ANPR calls", "P1", "Positive"],
    ["TC-ANPR-006", "ANPR", "Auth", "ANPR uses separate Basic Auth host", "ANPR_BASE_URL set", "1. Inspect request to /api/detect", "ANPR_USERNAME/PASSWORD", "Request to ANPR host not OCI; Basic Auth present", "P1", "Positive"],
    # Manual
    ["TC-MAN-001", "Manual", "status_check", "vehicleStatus=0 continues polling", "MANUAL_UPDATE after anpr_status=0", "1. status_check returns vehicleStatus 0", '{"vehicleStatus":0}', "Remain in manual loop; keep polling", "P1", "Positive"],
    ["TC-MAN-002", "Manual", "status_check", "vehicleStatus=1 grants entry", "MANUAL_UPDATE", "1. status_check returns vehicleStatus 1", '{"vehicleStatus":1}', "boom-close then boom open TL green; Entry Granted; WAIT_CROSSING", "P0", "Positive"],
    ["TC-MAN-003", "Manual", "status_check", "vehicleStatus=2 resets to IDLE", "MANUAL_UPDATE", "1. status_check returns vehicleStatus 2", '{"vehicleStatus":2}', "Reset IDLE; boom closed TL red; RFID prepare IDLE", "P0", "Positive"],
    # Boom
    ["TC-BOOM-001", "Hardware", "Boom", "boom-close status 200 opens boom", "ANPR match path", "1. boom-close returns status 200", '{"status":200}', "Boom OPEN; TL GREEN", "P0", "Positive"],
    ["TC-BOOM-002", "Hardware", "Boom", "boom-close failure does not open boom", "ANPR match path", "1. boom-close returns status 500", '{"status":500}', "Boom NOT opened; log Boom NOT opened", "P0", "Negative"],
    ["TC-BOOM-003", "Hardware", "Boom", "boom-close payload fields", "Grant entry", "1. Capture boom-close request", "rfid device_ip close-type=auto", "Payload has rfid device_ip close-type auto", "P1", "Positive"],
    # Sensor
    ["TC-SEN-001", "Sensor", "Crossing", "Idle sensor stays FALSE no reset", "State IDLE; boom closed", "1. Observe DI0 false 2. Optional TRUE then FALSE while IDLE", "sensor FALSE", "No boom/TL change; clear ignored in IDLE", "P1", "Positive"],
    ["TC-SEN-002", "Sensor", "Crossing", "During validation sensor pulse ignored", "RFID/ANPR in progress", "1. Pulse sensor TRUE then FALSE during validation", "DI0 pulse", "Cycle continues; no premature IDLE", "P1", "Positive"],
    ["TC-SEN-003", "Sensor", "Crossing", "After grant TRUE then FALSE clears gate", "WAIT_CROSSING; boom open TL green", "1. Sensor TRUE 2. Sensor FALSE", "FALSE->TRUE->FALSE", "Falling edge: boom CLOSED TL RED IDLE; RFID IDLE prepare", "P0", "Positive"],
    ["TC-SEN-004", "Sensor", "Crossing", "Rising edge alone does not close boom", "WAIT_CROSSING", "1. Sensor goes TRUE and stays TRUE", "sensor TRUE", "Boom remains OPEN until FALSE after occupied", "P0", "Negative"],
    ["TC-SEN-005", "Sensor", "Timeout", "Crossing timeout auto IDLE if no clear", "WAIT_CROSSING; vehicle_crossing_timeout set", "1. Do not clear sensor until timeout", "e.g. 60s", "Auto IDLE boom closed TL red after timeout", "P1", "Positive"],
    # Modbus / TL
    ["TC-HW-001", "Hardware", "Modbus", "Connect real Modbus controller", "DEMO_MODE=false; 192.168.31.89:502 up", "1. Start app 2. Check logs", "IP 192.168.31.89 port 502 slave 1", "ModbusTCP connected read_fc=2 write_fc=5; not DemoIO", "P0", "Positive"],
    ["TC-HW-002", "Hardware", "Modbus", "DEMO_MODE uses DemoIOController", "DEMO_MODE=true", "1. Start app", "DEMO_MODE=true", "Log DemoIOController connected", "P2", "Positive"],
    ["TC-HW-003", "Hardware", "TL", "IDLE applies TL red and boom closed", "App start or reset", "1. Observe DO0-DO3", "Idle hardware", "Red ON green OFF; boom close asserted", "P0", "Positive"],
    ["TC-HW-004", "Hardware", "TL", "Grant applies TL green", "Successful validation", "1. Observe after grant", "grant path", "Green ON red OFF", "P0", "Positive"],
    ["TC-HW-005", "Hardware", "Pins", "Pin mapping matches config", "iot_configuration loaded", "1. Check Hardware mapped log", "TL DO 0/1 boom DO 2/3 sensor DI 0", "Log matches mapping", "P1", "Positive"],
    ["TC-HW-006", "Hardware", "DI", "Read inputs use FC2 discrete inputs", "Real controller", "1. Monitor DI with app or modbus_tcp_app", "read_fc=2 di=0/8", "Sensor reads via FC2 address 0", "P1", "Positive"],
    ["TC-HW-007", "Hardware", "DO", "Write outputs use FC5 single coil", "Real controller", "1. Toggle TL/boom", "write_fc=5 do=0/8", "Coils written via FC5", "P1", "Positive"],
    # RFID cloud
    ["TC-CLD-001", "RFID Cloud", "IDLE", "IDLE prepare login mode start", "API RFID mode; reader HTTPS up", "1. Start app or reset IDLE", "reader IP from config", "login Basic then mode/start Bearer; reader scanning", "P0", "Positive"],
    ["TC-CLD-002", "RFID Cloud", "Stop", "Stop reader after tags received", "RFID tags accepted", "1. POST /rfid_data", "Valid tags", "cloud/stop before OCI validate", "P0", "Positive"],
    ["TC-CLD-003", "RFID Cloud", "API mode", "No TCP client to reader port 5555", "mode=API DEMO_MODE=false", "1. Start app 2. Watch logs", "mode API", "No WinError 10061 RFID client retries; status type=api", "P0", "Positive"],
    # Display
    ["TC-DSP-001", "Display", "MQTT", "RFID error message published", "RFID invalid", "1. Fail RFID validate", "OCI fail", "Display RFID ERR 1", "P1", "Positive"],
    ["TC-DSP-002", "Display", "MQTT", "Truck number published after RFID valid", "RFID valid", "1. Successful RFID validate", "vehicle from truck_details", "Display shows vehicle number", "P1", "Positive"],
    ["TC-DSP-003", "Display", "MQTT", "ANPR ERR 1 / Err-2 / API ERR", "Corresponding ANPR outcomes", "1. Force each ANPR path", "status 0 / 2 / API fail", "Correct display string for each path", "P1", "Positive"],
    ["TC-DSP-004", "Display", "MQTT", "Entry Granted message", "Grant path", "1. Complete grant", "truck no", "Display {truck} Entry Granted", "P1", "Positive"],
    # Config
    ["TC-CFG-001", "Config", "Env", "DEVICE_IP used in OCI payloads", "DEVICE_IP in .env", "1. Capture OCI POST", "DEVICE_IP value", "device_ip field matches env", "P1", "Positive"],
    ["TC-CFG-002", "Config", "Env", "ANPR_BASE_URL separate from OCI", "ANPR_BASE_URL set", "1. Trigger ANPR", "http://192.168.25.79:5001", "ANPR calls that host /api/detect", "P1", "Positive"],
    ["TC-CFG-003", "Config", "Timer", "vehicle_crossing_timeout from JSON", "iot_configuration set", "1. Grant without sensor", "e.g. 60", "Auto IDLE after configured seconds", "P2", "Positive"],
    ["TC-CFG-004", "Config", "Timer", "truck_anpr_retry_timer in manual loop", "anpr_status=0", "1. Observe status_check poll interval", "truck_anpr_retry_timer", "Polling interval matches config", "P2", "Positive"],
    # E2E
    ["TC-E2E-001", "E2E", "Happy path", "Full happy path reader RFID to IDLE", "Hardware+OCI+ANPR up; IDLE", "1. POST /rfid_data 2. OCI RFID 200 3. ANPR 1 4. boom-close 200 5. Sensor TRUE then FALSE", "Valid tag + match", "Grant then after clear: IDLE TL red boom closed", "P0", "Positive"],
    ["TC-E2E-002", "E2E", "Happy path", "Full happy path mobile RFID to IDLE", "Same as E2E-001", "1. POST /rfid_data_from_mobile_app 2. Rest same as E2E-001", "Valid rfid_data", "Same IDLE end; mobile got OCI validate JSON HTTP 200", "P0", "Positive"],
    ["TC-E2E-003", "E2E", "Manual path", "ANPR mismatch then manual approve", "RFID valid", "1. ANPR 0 2. status_check 1 3. Sensor clear", "vehicleStatus 0 then 1", "Grant after manual; sensor clear to IDLE", "P0", "Positive"],
    ["TC-E2E-004", "E2E", "Reject path", "ANPR Err-2 full cycle", "RFID valid", "1. ANPR status 2 2. Wait display timeout", "anpr_status 2", "ANPR Err-2 then IDLE without boom open", "P1", "Positive"],
    ["TC-E2E-005", "E2E", "Reject path", "RFID invalid full cycle", "IDLE", "1. Bad RFID 2. Wait 10s", "OCI RFID fail", "RFID ERR 1 then IDLE", "P1", "Positive"],
    # Robustness
    ["TC-ROB-001", "Robustness", "Concurrency", "Second RFID ignored while busy", "First cycle running", "1. Start cycle 2. Immediately POST another RFID", "Two tags", "Second ignored; first cycle completes", "P1", "Negative"],
    ["TC-ROB-002", "Robustness", "Network", "OCI timeout handling", "Block or slow OCI", "1. Trigger RFID validate", "timeout >15s", "Error handled; safe IDLE; no crash", "P2", "Negative"],
    ["TC-ROB-003", "Robustness", "Modbus", "Modbus disconnect resilience", "Controller unplugged", "1. Disconnect ethernet during IDLE/grant", "network drop", "Errors logged; app does not crash", "P2", "Negative"],
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(ROWS)
    print(f"Wrote {len(ROWS)} test cases -> {OUT}")


if __name__ == "__main__":
    main()
