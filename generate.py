#!/usr/bin/env python3
"""
Checklist Generator – YAML → PDF

Converts a structured YAML checklist definition into a print-ready
A4 landscape PDF with 4 columns and a centre fold margin.

Dependencies:
    pip install reportlab pyyaml

Font notes:
    Uses Arial via Liberation Sans (metrically identical, ships with most
    Linux distros). Falls back to Helvetica if TTF files are not found.

YAML format
-----------
meta:
  title:          "CHECKLIST  D-EPPT"
  subtitle:       "20.11.2024  Revision 1"
  fold_margin_mm: 8

columns:
  - col: 1
    sections:
      - title: BEFORE START
        type: normal        # normal | emergency | speeds
        items:
          - Parking Brake: SET
          - Power Lever: IDLE
          - "[note] (min. Drop 20 RPM)":
          - "[warn] EVACUATE":
          - "[blue] Throttle: 1200 RPM"
          - "[centered] — ON RWY —":
          - "[centered_blue] ABM THRESHOLD":
          - "[red] Emergency item: VALUE"

Item style prefixes (optional, in square brackets at start of key):
  (none)          normal: label left, callout right, dot leader
  [blue]          blue italic label and callout
  [warn]          red bold italic, full width, no callout
  [note]          small grey italic, indented, no callout
  [centered]      centred black bold
  [centered_blue] centred blue bold
  [red]           red bold label and callout

Speeds section (type: speeds):
  Items rendered as a two-column table (left half / right half), no dot leaders.
  Each item: "Label: VALUE" or "[red] Label: VALUE"
"""

import sys
import os
import argparse
import yaml
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    prog="generate.py",
    description="Convert a YAML checklist definition to a print-ready A4 landscape PDF.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
examples:
  python3 generate.py checklist.yaml
      → writes checklist.pdf in the same directory

  python3 generate.py checklist.yaml output/my-checklist.pdf
      → writes to a specific output path

  python3 generate.py --fold 10 checklist.yaml
      → override fold margin to 10 mm

  python3 generate.py --col-gap 4 --outer-margin 10 checklist.yaml out.pdf
    """,
)
parser.add_argument("input",  metavar="INPUT.yaml",  help="YAML checklist definition")
parser.add_argument("output", metavar="OUTPUT.pdf", nargs="?",
                    help="output PDF path (default: INPUT basename + .pdf)")
parser.add_argument("--fold", metavar="MM", type=float, default=None,
                    help="fold margin mm (overrides YAML meta value, fallback 8)")
parser.add_argument("--col-gap", metavar="MM", type=float, default=3.0,
                    help="gap between columns on the same half in mm (default: 3.0)")
parser.add_argument("--outer-margin", metavar="MM", type=float, default=12.7,
                    help="outer page margin mm (default: 12.7 = 0.5 inch)")
parser.add_argument("--scale", metavar="FACTOR", type=float, default=1.0,
                    help="font size multiplier (default: 1.0 = 100%%, e.g. 0.9 or 1.2)")
parser.add_argument("--line-spacing", metavar="FACTOR", type=float, default=1.35,
                    help="line height multiplier relative to font size (default: 1.35)")

args = parser.parse_args()
input_file  = args.input
output_file = args.output or os.path.splitext(input_file)[0] + ".pdf"

if not os.path.isfile(input_file):
    parser.error(f"Input file not found: {input_file}")

with open(input_file, encoding="utf-8") as f:
    data = yaml.safe_load(f)

# ── YAML item parser ──────────────────────────────────────────────────────────
# Items are standard YAML dicts:
#   - Parking Brake: SET          # normal item
#   - Throttle: 1200 RPM          # normal item
#     style: blue                 # optional style sub-key
#   - EVACUATE:                   # item with no callout
#     style: warn
#
# Valid style values:
#   blue / blue_italic   – blue italic label + callout
#   warn                 – red bold italic, full width
#   note                 – small grey italic, indented
#   centered             – centred black bold
#   centered_blue        – centred blue bold
#   red / red_bold       – red bold label + callout

_STYLE_MAP = {
    "blue":          "blue_italic",
    "blue_italic":   "blue_italic",
    "warn":          "warn",
    "note":          "note",
    "centered":      "centered_bold",
    "centered_bold": "centered_bold",
    "centered_blue": "centered_blue",
    "red":           "red_bold",
    "red_bold":      "red_bold",
}

def parse_item(raw):
    """Parse one YAML item dict into {"label", "callout", "style"}."""
    if isinstance(raw, str):
        # bare string with no value
        return {"label": raw.strip(), "callout": "", "style": "normal"}
    if not isinstance(raw, dict):
        return {"label": str(raw), "callout": "", "style": "normal"}

    # Extract optional style sub-key first, then the label/callout pair
    d = dict(raw)
    style_raw = d.pop("style", "normal")
    style = _STYLE_MAP.get(str(style_raw).lower().replace(" ", "_"), "normal")

    if not d:
        return {"label": "", "callout": "", "style": style}

    label, val = next(iter(d.items()))
    callout = str(val) if val is not None else ""
    return {"label": str(label).strip(), "callout": callout.strip(), "style": style}

# ── Font registration ─────────────────────────────────────────────────────────
_LIBERATION_PATHS = {
    "Arial":            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "Arial-Bold":       "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "Arial-Italic":     "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    "Arial-BoldItalic": "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
}
_FALLBACK = {
    "Arial": "Helvetica", "Arial-Bold": "Helvetica-Bold",
    "Arial-Italic": "Helvetica-Oblique", "Arial-BoldItalic": "Helvetica-BoldOblique",
}
_fonts_ok = all(os.path.isfile(p) for p in _LIBERATION_PATHS.values())
if _fonts_ok:
    for _name, _path in _LIBERATION_PATHS.items():
        pdfmetrics.registerFont(TTFont(_name, _path))
    print("  Font: Arial (via Liberation Sans TTF)")
else:
    print("  Font: Helvetica fallback (Liberation Sans TTF not found)")

def _font(key):
    return key if _fonts_ok else _FALLBACK[key]

FONT_NORMAL   = _font("Arial")
FONT_BOLD     = _font("Arial-Bold")
FONT_ITALIC   = _font("Arial-Italic")
FONT_BOLDITAL = _font("Arial-BoldItalic")

# ── Page geometry ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = landscape(A4)
OUTER_MARGIN   = args.outer_margin * mm
FOLD_MARGIN    = (args.fold if args.fold is not None
                  else data["meta"].get("fold_margin_mm", 8)) * mm
COL_GAP        = args.col_gap * mm

CONTENT_W = PAGE_W - 2 * OUTER_MARGIN
COL_W     = (CONTENT_W - 2 * COL_GAP - 2 * FOLD_MARGIN) / 4

def col_x(col_idx):
    x = OUTER_MARGIN + (col_idx - 1) * COL_W
    if col_idx >= 2: x += COL_GAP
    if col_idx >= 3: x += 2 * FOLD_MARGIN
    if col_idx >= 4: x += COL_GAP
    return x

CELL_PAD_X = 1.2 * mm

# ── Typography ────────────────────────────────────────────────────────────────
SCALE         = args.scale
SIZE_HEADER   = 6.5 * SCALE   # section title – larger + bold
SIZE_ITEM     = 4.8 * SCALE
SIZE_NOTE     = 4.0 * SCALE
SIZE_TITLE    = 7.5 * SCALE
SIZE_SUBTITLE = 5.0 * SCALE

HDR_BAR_H = 5.0 * mm * SCALE  # taller bar to fit larger title
ITEM_LEAD = SIZE_ITEM * 0.35278 * args.line_spacing * mm
NOTE_LEAD = SIZE_NOTE * 0.35278 * args.line_spacing * mm
SEC_GAP   = 1.2 * mm * SCALE  # tighter gap between sections (was 2.0)

# ── Colors ────────────────────────────────────────────────────────────────────
COL_TITLE_BG  = colors.HexColor("#2F5496")
COL_HEADER_BG = colors.black
COL_EMERG_BG  = colors.HexColor("#C00000")
COL_HEADER_FG = colors.white
COL_BLUE      = colors.HexColor("#2F5496")
COL_RED       = colors.HexColor("#C00000")
COL_BLACK     = colors.black
COL_GREY      = colors.HexColor("#555555")
COL_DOTS      = colors.HexColor("#999999")

# ── Canvas ────────────────────────────────────────────────────────────────────
c = canvas.Canvas(output_file, pagesize=landscape(A4))
c.setTitle(data["meta"]["title"])

def tw(text, font, size):
    return pdfmetrics.stringWidth(text, font, size)

# ── Title bar ─────────────────────────────────────────────────────────────────
def draw_title_bar():
    bar_h   = 7 * mm
    y_top   = PAGE_H - OUTER_MARGIN
    left_x  = col_x(1);  left_w  = col_x(2) + COL_W - left_x
    right_x = col_x(3);  right_w = col_x(4) + COL_W - right_x
    for x, w in [(left_x, left_w), (right_x, right_w)]:
        c.setFillColor(COL_TITLE_BG)
        c.rect(x, y_top - bar_h, w, bar_h, fill=1, stroke=0)
        c.setFillColor(COL_HEADER_FG)
        c.setFont(FONT_BOLD, SIZE_TITLE)
        c.drawString(x + CELL_PAD_X * 2, y_top - bar_h + 2.2 * mm, data["meta"]["title"])
        c.setFont(FONT_NORMAL, SIZE_SUBTITLE)
        sub = data["meta"]["subtitle"]
        c.drawString(x + w - tw(sub, FONT_NORMAL, SIZE_SUBTITLE) - CELL_PAD_X * 2,
                     y_top - bar_h + 2.5 * mm, sub)

# ── Dot leader ────────────────────────────────────────────────────────────────
def draw_dot_leader(cx, text_y, label, callout,
                    label_font, callout_font, label_color, callout_color, col_width):
    x_left  = cx + CELL_PAD_X
    x_right = cx + col_width - CELL_PAD_X
    lw = tw(label,   label_font,   SIZE_ITEM)
    cw = tw(callout, callout_font, SIZE_ITEM) if callout else 0

    c.setFillColor(label_color);   c.setFont(label_font,   SIZE_ITEM)
    c.drawString(x_left, text_y, label)
    if callout:
        c.setFillColor(callout_color); c.setFont(callout_font, SIZE_ITEM)
        c.drawRightString(x_right, text_y, callout)

    dot   = "."
    dot_w = tw(dot, FONT_NORMAL, SIZE_ITEM)
    gx0   = x_left + lw + 0.8 * mm
    gx1   = x_right - cw - 0.8 * mm
    gap   = gx1 - gx0
    if gap > dot_w * 2:
        n = int(gap / dot_w)
        s = gap / n
        c.setFillColor(COL_DOTS); c.setFont(FONT_NORMAL, SIZE_ITEM)
        for i in range(n):
            c.drawString(gx0 + i * s, text_y, dot)

# ── Speeds section ────────────────────────────────────────────────────────────
def render_speeds(section, cx, cy, col_width):
    """Two-column layout, no dot leaders, vertical divider in the middle."""
    items = [parse_item(i) for i in section.get("items", [])]
    mid   = (len(items) + 1) // 2
    left  = items[:mid]
    right = items[mid:]
    rows  = max(len(left), len(right))

    body_h  = rows * ITEM_LEAD + 1.0 * mm
    total_h = HDR_BAR_H + 0.5 * mm + body_h

    # Outer border
    c.setStrokeColor(COL_BLUE); c.setLineWidth(0.4)
    c.rect(cx, cy - total_h, col_width, total_h, fill=0, stroke=1)

    # Header bar
    c.setFillColor(COL_BLUE)
    c.rect(cx, cy - HDR_BAR_H, col_width, HDR_BAR_H, fill=1, stroke=0)
    c.setFillColor(COL_HEADER_FG); c.setFont(FONT_BOLD, SIZE_HEADER)
    ty = cy - HDR_BAR_H + (HDR_BAR_H - SIZE_HEADER * 0.35278 * mm) / 2
    c.drawCentredString(cx + col_width / 2, ty, section["title"])
    cy -= HDR_BAR_H + 0.5 * mm

    # Vertical centre divider
    half_w = col_width / 2
    c.setStrokeColor(COL_BLUE); c.setLineWidth(0.3)
    c.line(cx + half_w, cy, cx + half_w, cy - body_h + 1.0 * mm)

    def draw_speed_row(item, x, y, w):
        is_red  = item["style"] == "red_bold"
        col     = COL_RED if is_red else COL_BLACK
        text_y  = y - SIZE_ITEM * 0.35278 * mm
        c.setFillColor(col); c.setFont(FONT_NORMAL if not is_red else FONT_BOLD, SIZE_ITEM)
        c.drawString(x + CELL_PAD_X, text_y, item["label"])
        if item["callout"]:
            c.setFillColor(col); c.setFont(FONT_BOLD, SIZE_ITEM)
            c.drawRightString(x + w - CELL_PAD_X, text_y, item["callout"])

    row_y = cy
    for item in left:
        draw_speed_row(item, cx, row_y, half_w)
        row_y -= ITEM_LEAD
    row_y = cy
    for item in right:
        draw_speed_row(item, cx + half_w, row_y, half_w)
        row_y -= ITEM_LEAD

    return cy - body_h - SEC_GAP

# ── Section renderer ──────────────────────────────────────────────────────────
def render_section(section, cx, cy, col_width):
    sec_type = section.get("type", "normal")

    if sec_type == "speeds":
        return render_speeds(section, cx, cy, col_width)

    title = section["title"]
    items = [parse_item(i) for i in section.get("items", [])]

    body_h  = sum(NOTE_LEAD if i["style"] == "note" else ITEM_LEAD for i in items)
    total_h = HDR_BAR_H + 0.5 * mm + body_h

    bg = COL_EMERG_BG if sec_type == "emergency" else COL_HEADER_BG
    c.setStrokeColor(bg); c.setLineWidth(0.4)
    c.rect(cx, cy - total_h, col_width, total_h, fill=0, stroke=1)

    c.setFillColor(bg)
    c.rect(cx, cy - HDR_BAR_H, col_width, HDR_BAR_H, fill=1, stroke=0)
    c.setFillColor(COL_HEADER_FG); c.setFont(FONT_BOLD, SIZE_HEADER)
    text_y = cy - HDR_BAR_H + (HDR_BAR_H - SIZE_HEADER * 0.35278 * mm) / 2
    c.drawCentredString(cx + col_width / 2, text_y, title)
    cy -= HDR_BAR_H + 0.5 * mm

    for item in items:
        cy = render_item(item, cx, cy, col_width)

    return cy - SEC_GAP

# ── Item renderer ─────────────────────────────────────────────────────────────
def render_item(item, cx, cy, col_width):
    style   = item["style"]
    label   = item["label"]
    callout = item["callout"]
    text_y  = cy - SIZE_ITEM * 0.35278 * mm

    if style == "note":
        c.setFillColor(COL_GREY); c.setFont(FONT_ITALIC, SIZE_NOTE)
        c.drawString(cx + CELL_PAD_X + 1 * mm, cy - SIZE_NOTE * 0.35278 * mm, label)
        return cy - NOTE_LEAD
    if style == "warn":
        c.setFillColor(COL_RED); c.setFont(FONT_BOLDITAL, SIZE_ITEM)
        c.drawString(cx + CELL_PAD_X, text_y, label)
        return cy - ITEM_LEAD
    if style == "centered_bold":
        c.setFillColor(COL_BLACK); c.setFont(FONT_BOLD, SIZE_ITEM)
        c.drawCentredString(cx + col_width / 2, text_y, label)
        return cy - ITEM_LEAD
    if style == "centered_blue":
        c.setFillColor(COL_BLUE); c.setFont(FONT_BOLD, SIZE_ITEM)
        c.drawCentredString(cx + col_width / 2, text_y, label)
        return cy - ITEM_LEAD
    if style == "red_bold":
        draw_dot_leader(cx, text_y, label, callout,
                        FONT_BOLD, FONT_BOLD, COL_RED, COL_RED, col_width)
        return cy - ITEM_LEAD
    if style == "blue_italic":
        draw_dot_leader(cx, text_y, label, callout,
                        FONT_BOLDITAL, FONT_BOLDITAL, COL_BLUE, COL_BLUE, col_width)
        return cy - ITEM_LEAD
    draw_dot_leader(cx, text_y, label, callout,
                    FONT_NORMAL, FONT_BOLD, COL_BLACK, COL_BLACK, col_width)
    return cy - ITEM_LEAD

# ── Main ──────────────────────────────────────────────────────────────────────
TITLE_BAR_H = 7 * mm
Y_START     = PAGE_H - OUTER_MARGIN - TITLE_BAR_H - 1 * mm

draw_title_bar()
for col_data in data["columns"]:
    ci = col_data["col"]
    cx = col_x(ci)
    cy = Y_START
    for section in col_data["sections"]:
        cy = render_section(section, cx, cy, COL_W)

c.save()
print(f"✓  Generated: {output_file}")
