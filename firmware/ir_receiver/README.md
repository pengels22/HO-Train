# 11-channel Arduino Nano IR inputs

- `ir_receiver_nano_diagnostics.ino`: diagnostic sketch for 11 demodulated receiver outputs on D2–D12, emitting raw input transitions as JSON lines at 115200 baud.
- Not a locomotive ID decoder. The actual 4-byte IR packet format (including any coding/framing), timing and carrier must be matched to the M5 Atom locomotive IR transmitter and tested with all receivers.
- Nano pins D2–D12 are a provisional interface from `config/ir_receivers.yaml`. Validate the receiver module's power requirements and signal polarity before wiring.
- A standard Nano cannot independently decode eleven simultaneous arbitrary IR protocols with hardware interrupt channels alone. Use an appropriate multiplexing/edge sampling solution, MCU upgrade, or distributed receiver architecture if bench timings show a limitation.
- Keep train stops and checkpoint-fault policy on the Pi; this board reports observations only.
