# Zone safety

Zone state is one of CLEAR, RESERVED, OCCUPIED, UNKNOWN, or FAULT. A reservation may cover multiple consecutive zones for stopping distance. A locomotive entering a zone does not release its prior zone; release requires explicit consist-clearance evidence.

Manual joystick control changes a train's target to MANUAL but does not bypass zone conflicts. Unverified zones, stale or contradictory sensor observations, missing IR packets, occupied zones, and an unverified relay command must prohibit autonomous entry. Turnouts A-G have logically assigned common/straight/divergent reed inputs, but until their wiring is validated the commanded NC/NO relay state remains an open-loop assumption. Hardware-mode routing must remain disabled until topology, boundaries, relay assumptions, and sensor associations are verified.
