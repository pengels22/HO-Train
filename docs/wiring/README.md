# Wiring drawings

The master wiring document is **HO_Railroad_Complete_Wiring_and_Pinout.pdf** (two landscape vector pages), generated from the HO layout electrical design.

**Current status:** The owner-supplied two-page PDF is checked in at `HO_Railroad_Complete_Wiring_and_Pinout.pdf`. It remains a design drawing, not proof of functional or safe electrical commissioning.

Source document notes:
- A–G is the agreed seven-powered-turnout plan; repository currently includes an unverified H/turntable spur and must reconcile that difference.
- Reed magnetic track detectors replace the *track-location* Hall inputs once validated. Dedicated tipper Hall/IR GPIO sensors remain separate.
- GPIO12/13/16 yard relay pins and MCP 0x21 destination inputs were added provisionally to the drawing; verify actual wiring.
- No Raspberry Pi GPIO is assigned to a physical E-Stop in the current controller architecture. Stop propagation uses the dispatcher and controller-local watchdog/E-Stop protocols.
- The PDF is a design drawing, **not** a proof of functional or safe electrical commissioning.

## Install the actual PDF

From the repository root, after downloading the PDF from the chat attachment:

```sh
mkdir -p docs/wiring
cp "/path/to/HO_Railroad_Complete_Wiring_and_Pinout.pdf" "docs/wiring/HO_Railroad_Complete_Wiring_and_Pinout.pdf"
git add docs/wiring/HO_Railroad_Complete_Wiring_and_Pinout.pdf
git commit -m "docs: add complete railroad wiring and pinout PDF"
git push
```

Do not paste extracted PDF text or a similarly named substitute in place of this original two-page drawing.
