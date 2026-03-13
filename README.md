# Aviation Checklist Generator

A command-line tool that converts YAML checklist definitions into print-ready **A4 landscape PDFs** — designed for laminated cockpit checklists with a centre fold.

```
python3 generate.py deadx.yaml
```

---

## Features

- 4-column layout with configurable centre fold margin
- Split title bar (one per half) for clean folding
- Section types: **normal** (black header), **emergency** (red header), **speeds** (blue two-column table)
- Dot leaders between item label and callout
- Item styles: normal, blue italic, warn, note, centered, red bold
- All typography parameters controllable via CLI flags
- Font: Arial via Liberation Sans (metrically identical, no licence required)
- Pure Python, runs headless on Linux — no GUI needed

---

## Installation

### Requirements

- Python 3.8+
- `fonts-liberation` package (provides Arial-compatible TTF files)

```bash
# Debian / Ubuntu
sudo apt install fonts-liberation
```

### Setup with venv

```bash
# Clone or copy the project files into a directory
cd checklist-generator

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

To deactivate the venv later:

```bash
deactivate
```

---

## Usage

```
python3 generate.py INPUT.yaml [OUTPUT.pdf] [options]
```

If `OUTPUT.pdf` is omitted, the PDF is written next to the input file with the same basename.

### Examples

```bash
# Basic usage – writes deadx.pdf
python3 generate.py deadx.yaml

# Explicit output path
python3 generate.py deadx.yaml /tmp/checklist.pdf

# Smaller font for dense sections
python3 generate.py --scale 0.9 deadx.yaml

# Wider fold margin, tighter column gap
python3 generate.py --fold 10 --col-gap 2 deadx.yaml

# Looser line spacing
python3 generate.py --line-spacing 1.5 deadx.yaml
```

---

## Command-line Reference

| Argument | Default | Description |
|---|---|---|
| `INPUT.yaml` | *(required)* | Path to the YAML checklist definition |
| `OUTPUT.pdf` | `INPUT.pdf` | Output path (optional) |
| `--fold MM` | from YAML / `8` | Centre fold margin in mm (each side of the fold) |
| `--col-gap MM` | `3.0` | Gap between columns on the same half in mm |
| `--outer-margin MM` | `12.7` | Outer page margin in mm (default = 0.5 inch, matches original DOCX template) |
| `--scale FACTOR` | `1.0` | Font size multiplier — scales all `pt` values and bar heights proportionally |
| `--line-spacing FACTOR` | `1.35` | Line height multiplier relative to font size |

---

## YAML Format

```yaml
meta:
  title: "CHECKLIST  D-EPPT"
  subtitle: "D-EPPT    20.11.2024    Revision 1    RFR"
  fold_margin_mm: 8

columns:
  - col: 1
    sections:
      - title: BEFORE START
        type: normal
        items:
          - Parking Brake: SET
          - Mixture: FULL RICH
          - AVIONIC MASTER: "OFF"     # quote ON/OFF to avoid YAML boolean parsing
          - Throttle: 1200 RPM
            style: blue
          - (max. Drop 175 RPM):
            style: note
          - EVACUATE:
            style: warn

  - col: 4
    sections:
      - title: ENGINE FIRE IN FLIGHT
        type: emergency
        items:
          - Fuel Shut-off Value: CLOSED
          - Throttle: FULL FORWARD

      - title: OPERATING SPEEDS [KIAS]
        type: speeds
        items:
          - VR: "59"
          - VX: "66"
          - GLIDE: "73"
            style: red
```

### Section types

| Type | Header colour | Layout |
|---|---|---|
| `normal` | Black | Single column, dot leaders |
| `emergency` | Red | Single column, dot leaders |
| `speeds` | Blue | Two-column table, no dot leaders |

### Item styles

| Style | Appearance |
|---|---|
| *(none)* | Normal: label left, callout right, grey dot leader |
| `blue` | Blue italic label and callout |
| `warn` | Red bold italic, full width, no callout |
| `note` | Small grey italic, indented, no callout |
| `centered` | Centred black bold |
| `centered_blue` | Centred blue bold |
| `red` | Red bold label and callout |

### YAML gotchas

YAML interprets `ON`, `OFF`, `YES`, `NO`, `TRUE`, `FALSE` as booleans. Always quote these values:

```yaml
- AVIONIC MASTER: "OFF"   # correct
- AVIONIC MASTER: OFF     # parsed as boolean False — wrong
```

---

## Font Notes

The generator uses **Liberation Sans**, a metrically identical open-source substitute for Arial developed by Red Hat. It ships with most Linux distributions as part of the `fonts-liberation` package and produces output visually indistinguishable from Arial.

If the TTF files are not found at `/usr/share/fonts/truetype/liberation/`, the generator falls back to Helvetica (built into reportlab) with a warning.

To use actual Arial (e.g. on a system with Microsoft Core Fonts installed), update the `_LIBERATION_PATHS` dict in `generate.py` to point to the Arial TTF files.

---

## Project Files

| File | Description |
|---|---|
| `generate.py` | The generator script |
| `requirements.txt` | Python dependencies |
| `deadx.yaml` | Checklist for D-EADX (DA40 TDI) |
| `checklist-R200.yaml` | Checklist for D-EPPT (Robin R200) |
