# Aviation Checklist Generator

A tool for creating print-ready **A4 landscape PDF checklists** — designed for laminated cockpit cards with a centre fold. Normal procedures on the left half, emergency procedures on the right.

🌐 **Live demo: [checklists.helgenberger.net](https://checklists.helgenberger.net/)**

---

## Overview

The project has three components:

| File | Description |
|---|---|
| `generate.py` | CLI tool: YAML → PDF |
| `server.py` | Flask HTTP backend: `POST /generate` → PDF, serves `./public/` |
| `public/index.html` | Vue 3 web UI |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image, non-root, port 5000 |

Checklists are defined in YAML — see [`deadx.yaml`](deadx.yaml) (DA40 TDI) and [`deppt.yaml`](deppt.yaml) (Robin R200) for real-world examples.

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/helge000/checklists
cd checklists

# Place the UI
mkdir -p public
cp checklist-ui.html public/index.html

docker build -t checklist-generator .
docker run -p 5000:5000 checklist-generator
```

Open **http://localhost:5000** — the web UI lets you edit YAML, tune all layout options and generate PDFs directly in the browser.

### Local (venv)

```bash
# System fonts (Debian / Ubuntu)
sudo apt install fonts-liberation fonts-dejavu-core

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# CLI — generate a PDF directly
python3 generate.py deadx.yaml

# HTTP backend + UI
mkdir -p public && cp checklist-ui.html public/index.html
python3 server.py --host 0.0.0.0 --port 5000
```

---

## CLI Reference

```
python3 generate.py INPUT.yaml [OUTPUT.pdf] [options]
```

| Argument | Default | Description |
|---|---|---|
| `INPUT.yaml` | *(required)* | YAML checklist definition |
| `OUTPUT.pdf` | `INPUT.pdf` | Output path (optional) |
| `--columns N` | from YAML / `4` | Total columns 2–6 (left half: normal, right half: emergency) |
| `--fold MM` | `8` | Centre fold margin in mm (each side) |
| `--col-gap MM` | `3.0` | Gap between columns on the same half |
| `--outer-margin MM` | `8` | Outer page margin in mm |
| `--scale FACTOR` | `1.0` | Font size multiplier |
| `--line-spacing FACTOR` | `1.35` | Line height multiplier |
| `--font NAME` | `dejavu-condensed` | `arial` · `dejavu` · `dejavu-condensed` · `dejavu-mono` |
| `--monospaced` | — | Shorthand for `--font dejavu-mono` |

All options can also be set in the YAML `meta` block (CLI overrides YAML).

---

## HTTP API

```
POST /generate          YAML body → application/pdf
GET  /health            {"status": "ok", ...}
GET  /                  Serves ./public/index.html
GET  /<path>            Serves ./public/<path>
```

Query parameters mirror the CLI flags (`scale`, `columns`, `fold`, `col_gap`, `outer_margin`, `font`, `monospaced`, `line_spacing`).

```bash
curl -X POST "http://localhost:5000/generate?scale=1.2" \
     -H "Content-Type: application/yaml" \
     --data-binary @deadx.yaml \
     -o checklist.pdf
```

---

## YAML Format

```yaml
meta:
  callsign:        "D-EADX"
  icao_type:       "DA40"
  model:           "Diamond DA40 D TDI"
  revision:        "Rev 1  |  2024-11"
  columns:         6          # 4 or 6  (= 2 or 3 cols per half)
  font:            dejavu-condensed
  scale:           1.1
  line_spacing:    1.5
  fold_margin_mm:  8
  col_gap_mm:      3.0
  outer_margin_mm: 8

# Normal procedures — rendered on the LEFT half
normal:
  - col: 1
    sections:
      - title: "BEFORE START"
        header_color: black     # black | blue | green | yellow
        body_bg: false          # true = light grey background
        items:
          - Parking Brake: SET
          - AVIONIC MASTER: "OFF"   # quote ON/OFF — YAML reads them as booleans!
          - Throttle: 1200 RPM
            style: blue             # see Item Styles below
          - Wait for glow indicator:
            style: note

      - title: "OPERATING SPEEDS [KIAS]"
        type: speeds              # two-column table, no dot leaders
        body_bg: true
        items:
          - Vr: 59
          - Vne: 178
            style: red

# Emergency procedures — rendered on the RIGHT half
emergency:
  - col: 1                        # col 1 of the right half = col 4 on the page
    sections:
      - title: "ENGINE FAILURE AFTER T/O"
        items:
          - Glide: ESTABLISH
          - ENGINE MASTER: "OFF"
          - Mayday: TRANSMIT
            style: warn
          - EVACUATE:
            style: warn
```

### Item styles

| Style | Appearance | Typical use |
|---|---|---|
| *(none)* | Label left · callout right · dot leader | Standard item |
| `blue` | Blue italic, label + callout | Engine start steps |
| `note` | Small grey italic, indented | Limits, tolerances |
| `warn` | Red bold italic, full width | Critical warnings, EVACUATE |
| `centered` | Centred black bold | Phase dividers (— ON RWY —) |
| `centered_blue` | Centred blue bold | Sub-phase markers |
| `red` | Red bold, dot leader | Critical speeds (Vne, glide) |

### Section header colours

| Value | Colour | Suggested use |
|---|---|---|
| `black` | Black (default) | Before Start, Before T/O, Parking |
| `blue` | Dark blue `#2F5496` | Engine Start, Run Up, Approach |
| `green` | Forest green `#4E7A3A` | Taxi, Cruise, After Landing |
| `yellow` | Dark amber `#B8860B` | After Landing, Parking |

### YAML gotchas

YAML interprets `ON`, `OFF`, `YES`, `NO` as booleans. Always quote them:

```yaml
- AVIONIC MASTER: "OFF"   # ✓ correct
- AVIONIC MASTER: OFF     # ✗ parsed as boolean False
```

---

## Fonts

| CLI value | Font | Package |
|---|---|---|
| `dejavu-condensed` *(default)* | DejaVu Sans Condensed | `fonts-dejavu-core` |
| `dejavu` | DejaVu Sans | `fonts-dejavu-core` |
| `dejavu-mono` | DejaVu Sans Mono | `fonts-dejavu-core` |
| `arial` | Liberation Sans (Arial-compatible) | `fonts-liberation` |

Falls back to Helvetica (built into ReportLab) if TTF files are not found.

---

## License

[GPL v3](LICENSE) © 2026 [Daniel Helgenberger](https://github.com/helge000)
