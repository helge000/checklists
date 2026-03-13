#!/usr/bin/env python3
"""
Checklist Generator – JSON → PDF

Converts a structured JSON checklist definition into a print-ready
A4 landscape PDF with 4 columns and a centre fold margin.

Dependencies:
    pip install reportlab

Font notes:
    Uses Arial via Liberation Sans (metrically identical, ships with most
    Linux distros). Falls back to Helvetica if TTF files are not found.
    To use actual Arial, place Arial.ttf / Arial Bold.ttf / etc. in the
    same directory as this script and set FONT_DIR below.
"""

import sys
import os
import json
import argparse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    prog="generate.py",
    description="Convert a JSON checklist definition to a print-ready A4 landscape PDF.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
examples:
  python3 generate.py checklist-data.json
      → writes checklist-data.pdf in the same directory

  python3 generate.py checklist-data.json output/my-checklist.pdf
      → writes to a specific output path

  python3 generate.py --fold 10 checklist-data.json
      → use a 10 mm fold margin instead of the value in the JSON

json structure:
  {
    "meta": {
      "title":          "CHECKLIST  D-EPPT",
      "subtitle":       "20.11.2024  Revision 1",
      "fold_margin_mm": 8
    },
    "columns": [
      {
        "col": 1,
        "sections": [
          {
            "title": "BEFORE START",
            "type":  "normal",          // "normal" | "emergency" | "speeds"
            "items": [
              { "label": "Parking Brake", "callout": "SET" },
              { "label": "Note text",     "callout": "", "style": "note" }
            ]
          }
        ]
      }
    ]
  }

item styles:
  (default)       label left, callout right, dot leader between
  blue_italic     both label and callout in blue italic (e.g. engine start steps)
  red_bold        both in red bold
  warn            full-width red bold italic (no callout)
  note            small grey italic indent (no callout)
  centered_bold   centred black bold (e.g. decision points)
  centered_blue   centred blue bold

section types:
  normal          dark-blue header bar
  emergency       red header bar
  speeds          dark-blue header bar (same as normal)
    """,
)
parser.add_argument(
    "input",
    metavar="INPUT.json",
    help="path to the JSON checklist definition file",
)
parser.add_argument(
    "output",
    metavar="OUTPUT.pdf",
    nargs="?",
    help="path for the generated PDF (default: same name as INPUT with .pdf extension)",
)
parser.add_argument(
    "--fold",
    metavar="MM",
    type=float,
    default=None,
    help="override fold margin in mm (default: value from JSON meta, fallback 8 mm)",
)
parser.add_argument(
    "--col-gap",
    metavar="MM",
    type=float,
    default=3.0,
    help="gap between columns on the same half in mm (default: 3.0)",
)
parser.add_argument(
    "--outer-margin",
    metavar="MM",
    type=float,
    default=12.7,
    help="outer page margin in mm (default: 12.7 = 0.5 inch, matching original DOCX template)",
)

args = parser.parse_args()

input_file  = args.input
output_file = args.output or os.path.splitext(input_file)[0] + ".pdf"

if not os.path.isfile(input_file):
    parser.error(f"Input file not found: {input_file}")

with open(input_file, encoding="utf-8") as f:
    data = json.load(f)

# ── Font registration ─────────────────────────────────────────────────────────
# Liberation Sans is metrically identical to Arial and ships with most Linux
# distros. Falls back to built-in Helvetica if TTF files are not found.
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

# ── Page geometry (from original DOCX: 720 DXA = 12.7 mm margins) ────────────
PAGE_W, PAGE_H = landscape(A4)
OUTER_MARGIN   = args.outer_margin * mm
FOLD_MARGIN    = (args.fold if args.fold is not None else data["meta"].get("fold_margin_mm", 8)) * mm
COL_GAP        = args.col_gap * mm     # gap between columns on same half

CONTENT_W = PAGE_W - 2 * OUTER_MARGIN

# Layout: [OUTER][col1][GAP][col2][FOLD/2][|fold|][FOLD/2][col3][GAP][col4][OUTER]
# 4 cols + 2 inter-col gaps (one per half) + 2×FOLD_MARGIN (the fold gap, split)
COL_W = (CONTENT_W - 2 * COL_GAP - 2 * FOLD_MARGIN) / 4

def col_x(col_idx):
    """Left edge of column (1-indexed), in points from page left."""
    x = OUTER_MARGIN
    x += (col_idx - 1) * COL_W
    if col_idx >= 2:
        x += COL_GAP           # gap between col 1 and col 2
    if col_idx >= 3:
        x += 2 * FOLD_MARGIN   # fold gap between col 2 and col 3
    if col_idx >= 4:
        x += COL_GAP           # gap between col 3 and col 4
    return x

CELL_PAD_X = 1.2 * mm

# ── Typography ────────────────────────────────────────────────────────────────

SIZE_HEADER   = 5.0   # section header text (pt)
SIZE_ITEM     = 4.8   # checklist item (pt)
SIZE_NOTE     = 4.0   # sub-note
SIZE_TITLE    = 7.5   # document title bar
SIZE_SUBTITLE = 5.0

HDR_BAR_H  = 4.2 * mm                           # fixed header bar height
ITEM_LEAD  = SIZE_ITEM * 0.35278 * 1.55 * mm    # line height
NOTE_LEAD  = SIZE_NOTE * 0.35278 * 1.55 * mm
SEC_GAP    = 2.0 * mm                           # vertical gap between sections

# ── Colors ────────────────────────────────────────────────────────────────────
COL_HEADER_BG = colors.black          # normal sections: white text on black
COL_EMERG_BG  = colors.HexColor("#C00000")
COL_HEADER_FG = colors.white
COL_BLUE      = colors.HexColor("#2F5496")
COL_RED       = colors.HexColor("#C00000")
COL_BLACK     = colors.black
COL_GREY      = colors.HexColor("#555555")
COL_DOTS      = colors.HexColor("#999999")
COL_DIVIDER   = colors.HexColor("#CCCCCC")

# ── Canvas ────────────────────────────────────────────────────────────────────
c = canvas.Canvas(output_file, pagesize=landscape(A4))
c.setTitle(data["meta"]["title"])

def tw(text, font, size):
    return pdfmetrics.stringWidth(text, font, size)

# ── Title bar ─────────────────────────────────────────────────────────────────
def draw_title_bar():
    bar_h = 7 * mm
    y_top = PAGE_H - OUTER_MARGIN

    # Left half: col1 left edge → col2 right edge (including gap between them)
    left_x = col_x(1)
    left_w  = col_x(2) + COL_W - left_x
    # Right half: col3 left edge → col4 right edge
    right_x = col_x(3)
    right_w  = col_x(4) + COL_W - right_x

    for x, w in [(left_x, left_w), (right_x, right_w)]:
        c.setFillColor(COL_HEADER_BG)
        c.rect(x, y_top - bar_h, w, bar_h, fill=1, stroke=0)
        c.setFillColor(COL_HEADER_FG)
        c.setFont(FONT_BOLD, SIZE_TITLE)
        c.drawString(x + CELL_PAD_X * 2, y_top - bar_h + 2.2 * mm, data["meta"]["title"])
        c.setFont(FONT_NORMAL, SIZE_SUBTITLE)
        sub   = data["meta"]["subtitle"]
        sub_w = tw(sub, FONT_NORMAL, SIZE_SUBTITLE)
        c.drawString(x + w - sub_w - CELL_PAD_X * 2, y_top - bar_h + 2.5 * mm, sub)

# ── Column dividers ───────────────────────────────────────────────────────────
def draw_col_dividers(y_top, y_bottom):
    c.setStrokeColor(COL_DIVIDER)
    c.setLineWidth(0.3)
    for ci in range(1, 5):
        c.line(col_x(ci), y_bottom, col_x(ci), y_top)
    # right edge of last column
    c.line(col_x(4) + COL_W, y_bottom, col_x(4) + COL_W, y_top)

# ── Dot leader ────────────────────────────────────────────────────────────────
def draw_dot_leader(cx, text_y, label, callout,
                    label_font, callout_font,
                    label_color, callout_color, col_width):
    x_left  = cx + CELL_PAD_X
    x_right = cx + col_width - CELL_PAD_X

    lw = tw(label,   label_font,   SIZE_ITEM)
    cw = tw(callout, callout_font, SIZE_ITEM) if callout else 0

    # Label
    c.setFillColor(label_color)
    c.setFont(label_font, SIZE_ITEM)
    c.drawString(x_left, text_y, label)

    # Callout right-aligned
    if callout:
        c.setFillColor(callout_color)
        c.setFont(callout_font, SIZE_ITEM)
        c.drawRightString(x_right, text_y, callout)

    # Dot leader
    dot   = "."
    dot_w = tw(dot, FONT_NORMAL, SIZE_ITEM)
    gap_x0 = x_left + lw + 0.8 * mm
    gap_x1 = x_right - cw - 0.8 * mm
    gap    = gap_x1 - gap_x0
    if gap > dot_w * 2:
        n_dots  = int(gap / dot_w)
        spacing = gap / n_dots
        c.setFillColor(COL_DOTS)
        c.setFont(FONT_NORMAL, SIZE_ITEM)
        for i in range(n_dots):
            c.drawString(gap_x0 + i * spacing, text_y, dot)

# ── Section renderer ──────────────────────────────────────────────────────────
def render_section(section, cx, cy, col_width):
    sec_type = section.get("type", "normal")
    title    = section["title"]
    items    = section.get("items", [])

    # ---- Pre-calculate total section height for the border rect ----
    body_h = len(items) * ITEM_LEAD  # rough estimate; notes are slightly shorter
    for item in items:
        if item.get("style") == "note":
            body_h += NOTE_LEAD - ITEM_LEAD   # note rows are shorter
    total_h = HDR_BAR_H + 0.5 * mm + body_h

    # ---- Outer border around the entire section ----
    BORDER_W = 0.4
    c.setStrokeColor(COL_HEADER_BG if sec_type != "emergency" else COL_EMERG_BG)
    c.setLineWidth(BORDER_W)
    c.rect(cx, cy - total_h, col_width, total_h, fill=0, stroke=1)

    # ---- Header bar (filled, no stroke — border already drawn above) ----
    c.setFillColor(COL_EMERG_BG if sec_type == "emergency" else COL_HEADER_BG)
    c.rect(cx, cy - HDR_BAR_H, col_width, HDR_BAR_H, fill=1, stroke=0)
    c.setFillColor(COL_HEADER_FG)
    c.setFont(FONT_BOLD, SIZE_HEADER)
    text_y = cy - HDR_BAR_H + (HDR_BAR_H - SIZE_HEADER * 0.35278 * mm) / 2
    c.drawString(cx + CELL_PAD_X, text_y, title)
    cy -= HDR_BAR_H + 0.5 * mm

    for item in items:
        cy = render_item(item, cx, cy, col_width)

    return cy - SEC_GAP

# ── Item renderer ─────────────────────────────────────────────────────────────
def render_item(item, cx, cy, col_width):
    style   = item.get("style", "normal")
    label   = item.get("label", "")
    callout = item.get("callout", "")
    text_y  = cy - SIZE_ITEM * 0.35278 * mm

    if style == "note":
        c.setFillColor(COL_GREY)
        c.setFont(FONT_ITALIC, SIZE_NOTE)
        c.drawString(cx + CELL_PAD_X + 1 * mm, cy - SIZE_NOTE * 0.35278 * mm, label)
        return cy - NOTE_LEAD

    if style == "warn":
        c.setFillColor(COL_RED)
        c.setFont(FONT_BOLDITAL, SIZE_ITEM)
        c.drawString(cx + CELL_PAD_X, text_y, label)
        return cy - ITEM_LEAD

    if style == "centered_bold":
        c.setFillColor(COL_BLACK)
        c.setFont(FONT_BOLD, SIZE_ITEM)
        c.drawCentredString(cx + col_width / 2, text_y, label)
        return cy - ITEM_LEAD

    if style == "centered_blue":
        c.setFillColor(COL_BLUE)
        c.setFont(FONT_BOLD, SIZE_ITEM)
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

    # Default normal item
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
