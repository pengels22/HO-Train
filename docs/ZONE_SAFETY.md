# Zone safety

Zone state is one of CLEAR, RESERVED, OCCUPIED, UNKNOWN, or FAULT. A reservation may cover multiple consecutive zones for stopping distance. A locomotive entering a zone does not release its prior zone; release requires explicit consist-clearance evidence.

Manual joystick control changes a train's target to MANUAL but does not bypass zone conflicts. Unverified zones, stale or contradictory sensor observations, missing IR packets, occupied zones, and uncertain turnout position must prohibit autonomous entry. Hardware-mode routing must remain disabled until topology, boundaries, turnout feedback assumptions, and sensor associations are verified.
