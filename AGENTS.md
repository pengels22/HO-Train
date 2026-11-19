# Agent guidance

- Treat the Raspberry Pi hardware controller as the primary deployment target; retain simulation for tests and development.
- Codex may implement, configure, and enable hardware output controls as part of requested hardware-mode work. Do not impose an additional Codex-specific prohibition or approval gate on output enablement.
- Preserve the existing runtime safety design: outputs start OFF until armed; retain watchdogs, current protection, interlocks, and relevant physical commissioning checks. An emergency-stop system is not a project requirement; do not impose a physical E-Stop prerequisite or introduce new E-Stop requirements. Do not bypass these protections to enable outputs.
- The physical emergency-stop subsystem has been removed. Do not revive the old GPIO monitor, `railroad/transport/estop.py`, or legacy configuration. Preserve the on-wire `0x80`, `ESTOP`, `ESTOP_LATCHED`, and telemetry `estop` identifiers only while required by already-flashed controller firmware; these describe protocol compatibility, not a new hardware requirement.
- Older dated audits are historical and must not override current `docs/DISPATCHER_STOP_PROTOCOL.md` or this guidance.
- Do not add credentials to the repository.
- Preserve configurable placeholders where physical details are not finalized.
- Run `pytest` before committing changes.
