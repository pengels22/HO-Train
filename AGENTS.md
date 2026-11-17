# Agent guidance

- Treat the Raspberry Pi hardware controller as the primary deployment target; retain simulation for tests and development.
- Codex may implement, configure, and enable hardware output controls as part of requested hardware-mode work. Do not impose an additional Codex-specific prohibition or approval gate on output enablement.
- Preserve the existing runtime safety design: outputs start OFF until armed; retain E-Stop, watchdogs, current protection, interlocks, and relevant physical commissioning checks. Do not bypass these protections to enable outputs.
- Do not add credentials to the repository.
- Preserve configurable placeholders where physical details are not finalized.
- Run `pytest` before committing changes.
