# Wiring drawings

The master wiring document is **HO_Railroad_Complete_Wiring_and_Pinout.pdf** (two landscape vector pages), generated from the HO layout electrical design.

**Current status:** The attached PDF is not yet checked in. It must be copied into this directory from the owner's downloaded copy; do not commit a placeholder file under a .pdf extension.

Source document notes:
- A–G is the agreed seven-powered-turnout plan; repository currently includes an unverified H/turntable spur and must reconcile that difference.
- Reed magnetic track detectors replace the *track-location* Hall inputs once validated. Dedicated tipper Hall/IR GPIO sensors remain separate.
- GPIO12/13/16 yard relay pins and MCP 0x21 destination inputs were added provisionally to the drawing; verify actual wiring.
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
