# Central control tray — agreed physical design

30 x 30 inch open-air tray beneath layout, about 10 inches clear to underside of basement track supports. Access from mountain rear and beneath. Passive cooling.

- Upper left: Pi 4B, Mega 2560, Nano Classic, Nano ESP32.
- Middle left: powered USB 3.0 hub; reserve space for seven DRV8833 boards, placement pending.
- Upper right: 5V/18A and 12V/18A supplies. Vertically arranged fuse blocks on right, 5V above 12V, inputs right and outputs left.
- Vertical centerline: compact bank of twelve relays, contact terminals face right toward 12V half. Eight turnouts, three yard circuits, one spare. Relay control belongs to Nano Classic.
- Front: 30-inch DIN rail, grey 5V/I/O on left and blue 12V on right, flat terminal arrangement; mounting clearance for front connectors to be checked. Spring-clamp lever terminals. No mains on field rail.
- Front ports from left: HDMI (Pi), USB1 turntable, USB2 tipper, USB3 HID1, USB4 HID2. Four external USB ports connect to powered hub. Hub and three internal Arduinos occupy four direct Pi USB ports.
- 5V/18A supply powers Pi and Arduinos; safe single power path / USB backfeed prevention to be verified.
- 12V distribution feeds six mainline terminal pairs and three yard relays. Each yard relay feeds its own blue terminal pair; Track 1 shared 1A/1B. Turnouts 12V through blue terminals. Grey carries reeds, I/O and 5V distribution. Fuse every distribution branch to conductor and load ratings.

This is an equipment placement and wiring intent record, not an electrical installation drawing. Exact terminal schedule, driver mounting and fuse values remain pending.
