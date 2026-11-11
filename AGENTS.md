# GMDC Yard IoT — Agent Guide

## Scope

This repository contains the GMDC mine-yard IoT system. New runtime work belongs in
`Mines-Checkpoint`, `Mines-WB`, `gmdc_common`, `checkpoint-config`,
`digitizer-app`, `digitizer-decoder`, or `macos-services` as appropriate.
Legacy folders are reference-only unless a task explicitly targets them.

## Read first

- `docs/PROJECT_OVERVIEW.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/TECHNICAL_DECISIONS.md`
- `docs/CURRENT_STATUS.md`

## Non-negotiable decisions

- Do not change the verified Zebra CUSTOM configuration in
  `gmdc_common/gmdc_common/services/rfid_control.py` without explicit approval.
- Preserve strict Modbus function-code mapping: no FC1/FC2 fallback.
- Sensor reads are realtime-only; never invent or hold stale values after a failed read.
- Treat I/O health loss as a workflow safety lock.
- `Mines-Checkpoint` supports multiple isolated lanes in one process; preserve lane-specific
  Modbus, RFID, display, API-port, and filesystem behavior.
- Do not add a database dependency unless explicitly requested; current persistence is JSON,
  environment, filesystem, and service configuration.

## Change discipline

Read the relevant configuration and tests before editing. Keep secrets out of source and
documentation. Update tests and the knowledge base when an architectural decision changes.
Run the narrow tests first, then the relevant application suite.
