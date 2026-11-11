# Technical Decisions

This record captures decisions made in the repository and during the current
engineering work. It is intentionally concise; implementation details belong
in the source and architecture document.

## Runtime structure

1. **Use two current runtime families.** `Mines-Checkpoint` owns checkpoint
   locations; `Mines-WB` owns weighbridge flows. Legacy applications remain
   reference copies.
2. **Allow one Checkpoint process to host multiple lanes.** Each lane keeps
   its own reader, Modbus controller, display, API port, and workflow context.
3. **Use profiles for physical layout, not every business flow.**
   `checkpoint-config` canonical profiles are `checkpoint` and `weighbridge`.
   Legacy names normalize to those families; RFID validation selects the
   transaction flow.

## RFID

4. **Keep the verified Zebra CUSTOM configuration fixed.** The configuration
   in `gmdc_common/gmdc_common/services/rfid_control.py` uses antennas 5 and 6,
   TID selection, pointer 6, length 24, mask `800600`, 31/31 power, and
   per-antenna reporting. No change is authorized merely as cleanup.
5. **Use Zebra API mode for runtime intake.** The reader sends tags to the
   runtime HTTP endpoint; cloud login/mode/start/stop control remains separate.

## Modbus and safety

6. **Never cross-fallback function codes.** FC2 errors must not silently become
   FC1 reads, and output function codes are similarly strict.
7. **Prefer safety lock over uncertain actuation.** I/O health failure blocks
   new trips and aborts unsafe in-flight workflow actions.
8. **Use realtime sensor values only.** On read failure, clear/skip the sample;
   do not hold the previous occupied value or synthesize an edge.
9. **Debounce soft Modbus exceptions.** A soft exception is tolerated once. On
   the second failure in the digital-input path, reconnect and retry the read
   on the fresh socket. If that fresh attempt fails, the third failure marks
   I/O unhealthy. Hard transport errors remain immediate.
10. **Do not increase polling as a fault fix.** `polling.scan_interval` controls
    sampling; changing it does not correct a rejected Modbus request.

## Weighbridge and digitizer

11. **Mines-WB owns transaction stability and weight locking.** The decoder
    publishes current values; Mines-WB obtains a fresh stable sample after
    RFID/ANPR and locks it for the transaction.
12. **Keep decoder validation lightweight.** Decoder/API/MQTT return current
    weight; dashboard stability streaks are view-only.

## Operations

13. **Use macOS LaunchAgents for production runtime services.** Services need a
    stable install root, LAN wait, KeepAlive behavior, and separate logs.
14. **Use local Mosquitto.** TCP 1883 serves application clients and WebSocket
    9001 serves browser dashboards.
15. **Do not add a database without a requirement.** Current persistence is
    configuration JSON, environment, filesystem images, and logs.

## Open interpretation

The repository currently treats `mines_entry`, `tracking_1`, `tracking_2`, and
`mines_exit` as legacy aliases of the generic checkpoint profile. If those
locations require different API contracts, hardware layouts, or branding, they
must become explicit profiles rather than relying on lane labels.
