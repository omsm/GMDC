# Current Status

Status is based on the repository and the recorded engineering work. Items
marked "verified" are present in source/tests; items marked "site check" need
validation on the deployed machine or hardware.

## Completed / implemented

- Current runtime split: `Mines-Checkpoint` and `Mines-WB`.
- Multi-lane Checkpoint configuration and lane routing in one process.
- Per-lane RFID ports, reader mapping, display topics, and workflow contexts.
- Shared Modbus controller with strict FC1/FC2 reads and FC5/FC6 writes.
- No FC1/FC2 fallback after a failed transaction.
- Honest traffic-light and boom-barrier write state.
- Realtime-only sensor behavior; failed reads do not hold stale occupied state.
- I/O health lock, operator failure status, workflow abort/block, and recovery.
- Mines-WB far-side exit-before-weighbridge abort behavior.
- Mines-WB post-ANPR fresh stable-weight capture and transaction weight lock.
- Digitizer decoder current-weight-only MQTT/API behavior.
- Display MQTT handshake and per-location PCB topic conventions.
- Checkpoint crossing timeout and idle FTP image upload behavior.
- Zebra CUSTOM RFID JSON is fixed and accepted as correct:
  antennas 5/6, TID pointer 6, length 24, mask `800600`, 31/31 power,
  per-antenna reporting.
- Modbus soft-failure handling:
  - first soft exception: no offline lock
  - second soft exception on digital input: reconnect and fresh-read retry
  - successful retry: use the fresh sensor value
  - failed retry: third failure, mark I/O unhealthy
  - hard socket/transport failure: immediate resync/lock
- Unit tests cover the current I/O debounce and reconnect behavior.
- Product version **1.23** is reflected consistently in `version.md`, root and
  per-app READMEs, and `docs/PROJECT_OVERVIEW.md`.

## Pending implementation or verification

- Deploy the shared `gmdc_common` changes to the target site and restart the
  service; local source changes do not update an installed editable/non-editable
  package automatically.
- Run the complete Mines-Checkpoint and Mines-WB test suites in an environment
  with their declared dependencies.
- Confirm LaunchAgent/service configuration starts exactly one runtime instance.
- Validate every lane's Modbus IP, slave ID, DI/DO addresses, RFID reader IP,
  listener port, display IP/topic, camera, and endpoint settings on site.
- Observe post-deployment logs for soft-fail counts, reconnect success, and
  actual controller recovery.
- Decide whether legacy checkpoint IDs need separate commissioning profiles or
  whether generic `checkpoint` plus RFID-selected flows is sufficient.
- Remove or update stale/duplicate sample configuration files only after
  identifying which are used by deployment tooling.

## Known issues and risks

1. **Intermittent controller exception responses.** The site log showed FC2
   exception response `130 / 0`, mostly on DI address 1. The app-level debounce
   reduces false lock flashes but cannot repair noisy wiring, an unsupported
   address, a gateway fault, or a controller-side FC2 problem.
2. **Soft-failure scope is asymmetric.** The reconnect-before-fresh-read
   behavior was added to the digital-input path used by the tare WB. FC1 coil
   reads and output-write paths do not have the same second-failure fresh-read
   sequence.
3. **Checkpoint profile flattening.** `checkpoint-config` normalizes legacy
   names to generic `checkpoint`; lane labels do not by themselves create
   distinct API/branding/business profiles.
4. **Configuration naming inconsistency.** Some files use `wb_type`,
   `checkpoint_type`, `lane_id`, and `lane_name` inconsistently. Runtime
   loaders support several legacy forms, but commissioning should standardize
   the deployed format.
5. **No durable transaction database.** In-memory workflow state is lost on
   process restart; logs and images are filesystem artifacts.
6. **Secrets in operational configuration.** Reader, API, RTSP, and FTP
   credentials may be present in local `.env`/JSON files. Do not copy them
   into documentation or public commits.
7. **Development Flask server.** Runtime logs warn that the built-in Flask
   server is not a production WSGI server. This may be an accepted site
   deployment decision but should be reviewed.

## Recent site-log finding

The reviewed `mines_wb-2.log` showed sequential service starts and shutdowns,
not clear concurrent Mines-WB instances. It showed several FC2 exception
responses followed by immediate reconnects under the old policy. The new
policy must be verified in a fresh post-deployment log.
