"""Generate docs/Mines_Entry_Use_Cases.csv for Tracking Point."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "Mines_Entry_Use_Cases.csv"

HEADERS = [
    "UC_ID",
    "Positive/Negative",
    "Test Scenario Description",
    "Test Scenario Steps",
    "Remarks",
]

ROWS = [
    [
        "UC-001",
        "Positive",
        "Application health check - verify Tracking Point service is up",
        "1. Start the Tracking Point application.\n2. Send GET request to /.\n3. Verify response service name and status.",
        "Expected HTTP 200 with service=GMDC Tracking Point. Base smoke check before other UCs.",
    ],
    [
        "UC-002",
        "Positive",
        "View current application state and hardware snapshot",
        "1. Ensure application is running.\n2. Send GET /api/status.\n3. Verify state (e.g. IDLE) and hardware/transaction fields.",
        "Used by operators/support to confirm IDLE/busy and I/O status.",
    ],
    [
        "UC-003",
        "Positive",
        "Force reset application to IDLE safe state",
        "1. Put application in any non-IDLE state if needed.\n2. Send POST /api/reset.\n3. Verify state returns to IDLE.\n4. Verify traffic light RED and boom CLOSED.\n5. Verify RFID reader IDLE prepare (login/mode/start) if cloud enabled.",
        "Emergency / recovery use case. Clears transaction and sensor latch.",
    ],
    [
        "UC-004",
        "Positive",
        "Idle hardware initialize - TL red and boom closed on startup",
        "1. Set DEMO_MODE=false and correct Modbus IP.\n2. Start application.\n3. Observe DO coils and logs.\n4. Confirm TrafficLight RED and BoomBarrier CLOSED.",
        "Controller 192.168.31.89:502; DO0=red DO1=green DO2=open DO3=close.",
    ],
    [
        "UC-005",
        "Positive",
        "Connect to real Modbus I/O controller (FC2 DI / FC5 DO)",
        "1. Set DEMO_MODE=false in .env.\n2. Confirm iot_configuration ethernet IP 192.168.31.89 port 502 slave 1.\n3. Start application.\n4. Verify log ModbusTCP connected read_fc=2 write_fc=5.",
        "Must NOT use DemoIOController when running on site hardware.",
    ],
    [
        "UC-006",
        "Negative",
        "Demo mode uses in-memory I/O instead of real controller",
        "1. Set DEMO_MODE=true.\n2. Start application.\n3. Verify DemoIOController connected in logs.\n4. Confirm no Modbus TCP connection to controller.",
        "Useful for offline unit/integration testing only.",
    ],
    [
        "UC-007",
        "Positive",
        "RFID API mode - no TCP client to reader port",
        "1. Ensure rfids.entry_a.mode=API in iot_configuration.\n2. Start application with DEMO_MODE=false.\n3. Confirm no WinError 10061 RFID client retry logs.\n4. Confirm RFID status type=api.",
        "Tags arrive via HTTP POST /rfid_data; cloud login/start/stop via HTTPS.",
    ],
    [
        "UC-008",
        "Positive",
        "RFID cloud IDLE prepare - login then mode then start",
        "1. Application reaches IDLE.\n2. Observe RFID cloud calls: localRestLogin (Basic) → mode (Bearer) → start (Bearer).\n3. Confirm reader is scanning for next vehicle.",
        "Runs on bootstrap and after each reset to IDLE.",
    ],
    [
        "UC-009",
        "Positive",
        "Receive valid RFID tags from fixed reader via /rfid_data",
        "1. Ensure state is IDLE.\n2. Reader (or tool) POSTs Zebra tag JSON to /rfid_data with idHex.\n3. Verify HTTP 200 status=success and tags list.\n4. Verify RFID cloud stop is called.\n5. Verify OCI rfid-validate is invoked.",
        "Primary site path when Zebra FX pushes tags to self-hosted API.",
    ],
    [
        "UC-010",
        "Negative",
        "Reject /rfid_data when payload has no idHex tags",
        "1. POST /rfid_data with empty list [].\n2. Verify HTTP 400.\n3. Verify workflow does not start.",
        "Protects against empty/keepalive noise without tags.",
    ],
    [
        "UC-011",
        "Negative",
        "Ignore RFID tags when application is not IDLE",
        "1. Start a cycle so state is not IDLE (e.g. WAIT_CROSSING).\n2. POST another valid /rfid_data payload.\n3. Verify new cycle is not started.\n4. Verify log Ignoring RFID tags while in state …",
        "Prevents overlapping vehicle transactions.",
    ],
    [
        "UC-012",
        "Positive",
        "RFID management keepalive from reader",
        "1. POST /rfid_management with any JSON body.\n2. Verify HTTP 200 status=success.",
        "Reader keepalive; does not start workflow.",
    ],
    [
        "UC-013",
        "Positive",
        "Mobile app RFID fallback - valid tag returns OCI validate response",
        "1. Ensure state IDLE (fixed reader unavailable/damaged tag case).\n2. Mobile app POSTs {\"rfid_data\":\"<tag>\"} to /rfid_data_from_mobile_app.\n3. Verify HTTP 200.\n4. Verify response body is exactly OCI rfid-validate JSON.\n5. Verify background flow continues (ANPR etc.).",
        "Mobile replaces physical reader when RFID cannot be read at gate.",
    ],
    [
        "UC-014",
        "Negative",
        "Mobile RFID - missing rfid_data key",
        "1. POST /rfid_data_from_mobile_app with {}.\n2. Verify HTTP 500.\n3. Verify body status=500 rfid_data=null message Error: …",
        "Client validation failure; workflow not started.",
    ],
    [
        "UC-015",
        "Negative",
        "Mobile RFID - blank rfid_data value",
        "1. POST {\"rfid_data\":\"   \"}.\n2. Verify HTTP 500 and rfid_data=null.\n3. Verify workflow not started.",
        "Blank/whitespace treated as invalid.",
    ],
    [
        "UC-016",
        "Positive",
        "OCI RFID validate success - display truck and proceed to ANPR",
        "1. Trigger RFID (reader or mobile) with a tag OCI accepts.\n2. Verify OCI rfid-tag returns status 200 with truck_details.\n3. Verify display shows vehicle number.\n4. Verify ANPR /api/detect is called next.",
        "truck_details pipe string parsed for vehicle_no token_no device_ip.",
    ],
    [
        "UC-017",
        "Negative",
        "OCI RFID validate failure - RFID ERR 1 then auto IDLE",
        "1. Trigger RFID with invalid/unknown tag.\n2. Verify OCI returns non-200 (e.g. status 500).\n3. Verify display shows RFID ERR 1.\n4. Wait RFID error display timeout (~10s).\n5. Verify state returns IDLE; boom closed TL red.",
        "For mobile path HTTP to client is still 200 with OCI error body.",
    ],
    [
        "UC-018",
        "Positive",
        "ANPR match (anpr_status=1) - grant entry after boom-close OK",
        "1. Complete successful RFID validate.\n2. ANPR /api/detect returns anpr_status=1.\n3. Verify invalid-truck-number is posted.\n4. Verify boom-close API called with close-type=auto.\n5. If boom-close status=200: boom OPEN TL GREEN; display Entry Granted.\n6. State WAIT_CROSSING.",
        "Happy-path automatic grant.",
    ],
    [
        "UC-019",
        "Negative",
        "ANPR match but boom-close fails - boom must not open",
        "1. Reach ANPR anpr_status=1 path.\n2. boom-close returns status != 200.\n3. Verify boom remains CLOSED.\n4. Verify log Boom NOT opened.",
        "Safety gate: physical boom open only after OCI boom-close success.",
    ],
    [
        "UC-020",
        "Positive",
        "ANPR mismatch (anpr_status=0) - ANPR ERR 1 and manual status_check loop",
        "1. RFID valid.\n2. ANPR returns anpr_status=0.\n3. Verify invalid-truck posted.\n4. Verify display ANPR ERR 1.\n5. Verify periodic status_check polling starts.",
        "Operator/manual correction path via OCI status_check.",
    ],
    [
        "UC-021",
        "Positive",
        "Manual loop vehicleStatus=1 - grant entry",
        "1. Enter MANUAL_UPDATE after anpr_status=0.\n2. status_check returns vehicleStatus=1.\n3. Verify boom-close then boom open / TL green / Entry Granted.\n4. Enter WAIT_CROSSING.",
        "Manual approval after mismatch.",
    ],
    [
        "UC-022",
        "Negative",
        "Manual loop vehicleStatus=2 - reject and reset IDLE",
        "1. Enter MANUAL_UPDATE.\n2. status_check returns vehicleStatus=2.\n3. Verify reset to IDLE; boom closed TL red.",
        "Manual reject / abort transaction.",
    ],
    [
        "UC-023",
        "Positive",
        "Manual loop vehicleStatus=0 - continue waiting",
        "1. Enter MANUAL_UPDATE.\n2. status_check returns vehicleStatus=0 multiple times.\n3. Verify application stays in manual loop and keeps polling.",
        "Pending operator action; no grant yet.",
    ],
    [
        "UC-024",
        "Negative",
        "ANPR anpr_status=2 - ANPR Err-2 then wait and reset",
        "1. RFID valid.\n2. ANPR returns anpr_status=2.\n3. Verify display ANPR Err-2.\n4. Wait configured ANPR Err-2 display seconds.\n5. Verify IDLE; boom not opened.",
        "Hard ANPR reject path (no manual loop).",
    ],
    [
        "UC-025",
        "Negative",
        "ANPR API unreachable - retry 3 times then ANPR API ERR",
        "1. RFID valid.\n2. Make ANPR host unreachable / throw connection error.\n3. Verify up to 3 detect attempts with delay.\n4. Verify display ANPR API ERR.\n5. Verify reset IDLE; boom not opened.",
        "Transport failure handling; does not call invalid-truck if ANPR never succeeds.",
    ],
    [
        "UC-026",
        "Positive",
        "ANPR recovers on retry - grant after transient failure",
        "1. RFID valid.\n2. First ANPR call fails; second returns anpr_status=1.\n3. Verify grant path proceeds normally.",
        "Transient network/API flake tolerance.",
    ],
    [
        "UC-027",
        "Positive",
        "Vehicle crossing - sensor FALSE→TRUE→FALSE closes gate",
        "1. Complete grant so boom OPEN TL GREEN (WAIT_CROSSING).\n2. Confirm sensor idle FALSE.\n3. Truck on sensor → TRUE (occupied).\n4. Truck clears → FALSE (falling edge).\n5. Verify boom CLOSED TL RED state IDLE.\n6. Verify RFID IDLE prepare for next vehicle.",
        "Falling-after-occupied edge detection; DI0 entry sensor.",
    ],
    [
        "UC-028",
        "Negative",
        "Sensor rising edge alone must not close boom",
        "1. Reach WAIT_CROSSING with boom open.\n2. Drive sensor to TRUE and keep it TRUE.\n3. Verify boom stays OPEN and state remains WAIT_CROSSING.",
        "Close only after clear (TRUE then FALSE).",
    ],
    [
        "UC-029",
        "Negative",
        "Sensor activity during IDLE/validation must not reset cycle",
        "1. While IDLE or during RFID/ANPR validation pulse sensor TRUE then FALSE.\n2. Verify boom/TL not incorrectly changed by crossing clear.\n3. Verify no premature IDLE reset of an active validation cycle.",
        "Crossing-clear ignored unless ENTRY_GRANTED/WAIT_CROSSING.",
    ],
    [
        "UC-030",
        "Positive",
        "Crossing timeout - auto IDLE if truck never clears sensor",
        "1. Grant entry (WAIT_CROSSING).\n2. Do not complete sensor clear sequence.\n3. Wait vehicle_crossing_timeout from iot_configuration.\n4. Verify auto IDLE; boom closed TL red.",
        "Safety timeout if sensor miss or vehicle stalled.",
    ],
    [
        "UC-031",
        "Positive",
        "Simulate sensor clear via API (demo/helper)",
        "1. Reach WAIT_CROSSING (demo I/O or configured simulate).\n2. POST /api/simulate-exit.\n3. Verify pulse TRUE then FALSE and reset to IDLE hardware.",
        "Lab/demo helper when physical sensor not available.",
    ],
    [
        "UC-032",
        "Positive",
        "Display publishes RFID ERR 1 on validate failure",
        "1. Trigger invalid RFID.\n2. Verify MQTT/display shows RFID ERR 1.",
        "Operator-visible error messaging.",
    ],
    [
        "UC-033",
        "Positive",
        "Display publishes truck number after RFID success",
        "1. Trigger valid RFID.\n2. Verify display shows vehicle number from truck_details.",
        "Driver/operator feedback before ANPR.",
    ],
    [
        "UC-034",
        "Positive",
        "Display publishes Entry Granted after successful grant",
        "1. Complete ANPR match or manual approve with boom-close OK.\n2. Verify display shows {truck} Entry Granted.",
        "Confirms gate open authorization to user.",
    ],
    [
        "UC-035",
        "Positive",
        "End-to-end happy path - reader RFID to IDLE after clear",
        "1. IDLE.\n2. POST /rfid_data valid tag.\n3. OCI RFID 200.\n4. ANPR anpr_status=1.\n5. boom-close 200 → boom open TL green.\n6. Sensor TRUE then FALSE.\n7. Verify IDLE ready for next truck.",
        "Full production reader path.",
    ],
    [
        "UC-036",
        "Positive",
        "End-to-end happy path - mobile RFID to IDLE after clear",
        "1. IDLE.\n2. POST /rfid_data_from_mobile_app with valid rfid_data.\n3. Client receives OCI validate JSON (HTTP 200).\n4. ANPR 1 + boom-close 200.\n5. Sensor TRUE then FALSE → IDLE.",
        "Full production mobile fallback path.",
    ],
    [
        "UC-037",
        "Positive",
        "End-to-end manual approve path after ANPR mismatch",
        "1. RFID valid.\n2. ANPR anpr_status=0 → ANPR ERR 1.\n3. status_check eventually vehicleStatus=1.\n4. Grant hardware.\n5. Sensor clear → IDLE.",
        "Covers mismatch + operator correction.",
    ],
    [
        "UC-038",
        "Negative",
        "Concurrent second RFID ignored while cycle busy",
        "1. Start first RFID cycle.\n2. Immediately send second RFID (reader or mobile).\n3. Verify second is rejected/ignored.\n4. Verify first cycle completes without corruption.",
        "Single-transaction lock / state guard.",
    ],
    [
        "UC-039",
        "Positive",
        "OCI payloads include configured DEVICE_IP",
        "1. Set DEVICE_IP in .env.\n2. Trigger RFID validate / boom-close / invalid-truck.\n3. Verify device_ip in request bodies matches env.",
        "Site identity for OCI checkpoint APIs.",
    ],
    [
        "UC-040",
        "Positive",
        "ANPR calls separate host with its own Basic Auth",
        "1. Configure ANPR_BASE_URL and ANPR_USERNAME/PASSWORD.\n2. Trigger ANPR detect.\n3. Verify request goes to ANPR host /api/detect not OCI base.\n4. Verify ANPR Basic Auth used.",
        "ANPR service is independent of OCI ORDS host.",
    ],
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(ROWS)
    print(f"Wrote {len(ROWS)} use cases -> {OUT}")


if __name__ == "__main__":
    main()
