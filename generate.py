#!/usr/bin/env python3
"""
Checklist Generator – YAML → PDF

Converts a structured YAML checklist definition into a print-ready
A4 landscape PDF with 4–6 columns and a centre fold.
Normal procedures go on the left half, emergency procedures on the right.

Dependencies:
    pip install reportlab pyyaml

YAML structure
--------------
meta:
  title:          "CHECKLIST D-EADX"
  subtitle:       "DA40D TD155"

  # Layout (all optional, CLI flags override)
  fold_margin_mm: 8          # fold margin each side in mm
  col_gap_mm:     3.0        # gap between columns on the same half
  outer_margin_mm: 12.7      # page margin mm (0.5 inch)
  columns:        6          # total columns (2–6); left half = ceil(N/2)
  font:           dejavu-condensed   # arial | dejavu | dejavu-condensed | dejavu-mono
  monospaced:     false      # true = dejavu-mono (overrides font)
  scale:          1.0        # font size multiplier
  line_spacing:   1.35       # line height multiplier

normal:           # sections for the LEFT half, assigned to columns 1..ceil(N/2)
  - col: 1
    sections:
      - title: BEFORE START
        type: normal
        items:
          - Parking Brake: SET
          - AVIONIC MASTER: "OFF"   # quote ON/OFF to avoid YAML boolean parsing
          - Throttle: 1200 RPM
            style: blue             # blue | warn | note | centered | centered_blue | red
          - (note text):
            style: note

emergency:        # sections for the RIGHT half, assigned to columns 1..floor(N/2)
  - col: 1
    sections:
      - title: ENGINE FAILURE
        type: emergency
        items:
          - Glide: ESTABLISH
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

# ── Defaults (overridden by YAML meta, then by CLI) ──────────────────────────
DEFAULTS = {
    "fold_margin_mm":  8.0,
    "col_gap_mm":      3.0,
    "outer_margin_mm": 8,
    "columns":         4,
    "font":            "dejavu-condensed",
    "monospaced":      False,
    "scale":           1.0,
    "line_spacing":    1.35,
}

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    prog="generate.py",
    description="Convert a YAML checklist definition to a print-ready A4 landscape PDF.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Priority: CLI flag > YAML meta > built-in default

examples:
  python3 generate.py deadx.yaml
  python3 generate.py deadx.yaml output/checklist.pdf
  python3 generate.py --scale 0.9 --columns 6 deadx.yaml
  python3 generate.py --monospaced deadx.yaml

All layout options can also be set in the YAML meta block:
  meta:
    columns:         6
    font:            dejavu-condensed
    scale:           1.1
    line_spacing:    1.3
    fold_margin_mm:  10
    col_gap_mm:      2.5
    outer_margin_mm: 10
    """,
)
parser.add_argument("input",  metavar="INPUT.yaml")
parser.add_argument("output", metavar="OUTPUT.pdf", nargs="?",
                    help="output PDF (default: INPUT.pdf)")
parser.add_argument("--fold",         metavar="MM",     type=float, default=None,
                    help=f"fold margin mm (default: {DEFAULTS['fold_margin_mm']})")
parser.add_argument("--col-gap",      metavar="MM",     type=float, default=None,
                    help=f"inter-column gap mm (default: {DEFAULTS['col_gap_mm']})")
parser.add_argument("--outer-margin", metavar="MM",     type=float, default=None,
                    help=f"outer page margin mm (default: {DEFAULTS['outer_margin_mm']})")
parser.add_argument("--columns",      metavar="N",      type=int,   default=None,
                    help="total columns 2–6 (left half: normal, right half: emergency)")
parser.add_argument("--font",         metavar="NAME",   default=None,
                    choices=["arial", "dejavu", "dejavu-condensed", "dejavu-mono"],
                    help=f"font family (default: {DEFAULTS['font']})")
parser.add_argument("--monospaced",   action="store_true",
                    help="use DejaVu Sans Mono (shorthand for --font dejavu-mono)")
parser.add_argument("--scale",        metavar="FACTOR", type=float, default=None,
                    help=f"font size multiplier (default: {DEFAULTS['scale']})")
parser.add_argument("--line-spacing", metavar="FACTOR", type=float, default=None,
                    help=f"line height multiplier (default: {DEFAULTS['line_spacing']})")

args = parser.parse_args()
input_file  = args.input
output_file = args.output or os.path.splitext(input_file)[0] + ".pdf"

if not os.path.isfile(input_file):
    parser.error(f"Input file not found: {input_file}")

with open(input_file, encoding="utf-8") as f:
    data = yaml.safe_load(f)

meta = data.get("meta", {})

def cfg(key, cli_val, meta_key=None):
    """Resolve: CLI > YAML meta > default."""
    if cli_val is not None:
        return cli_val
    return meta.get(meta_key or key, DEFAULTS[key])

FOLD_MARGIN    = cfg("fold_margin_mm",  args.fold,         "fold_margin_mm")  * mm
COL_GAP        = cfg("col_gap_mm",      args.col_gap,      "col_gap_mm")      * mm
OUTER_MARGIN   = cfg("outer_margin_mm", args.outer_margin, "outer_margin_mm") * mm
SCALE          = cfg("scale",           args.scale,        "scale")
LINE_SPACING   = cfg("line_spacing",    args.line_spacing, "line_spacing")
N_COLS         = max(2, min(6, int(cfg("columns", args.columns, "columns"))))
_font_cli      = "dejavu-mono" if args.monospaced else args.font
_font_meta     = "dejavu-mono" if meta.get("monospaced") else meta.get("font")
FONT_CHOICE    = _font_cli or _font_meta or DEFAULTS["font"]

# ── YAML structure: normal / emergency → columns ──────────────────────────────
# The YAML has two top-level lists: `normal` and `emergency`.
# Each is a list of {col: N, sections: [...]} dicts.
# normal  → rendered on the LEFT  half (columns 1 … _left_cols)
# emergency → rendered on the RIGHT half (columns 1 … _right_cols, offset by _left_cols)
_left_cols  = (N_COLS + 1) // 2
_right_cols = N_COLS // 2

# ── YAML item parser ──────────────────────────────────────────────────────────
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
    if isinstance(raw, str):
        return {"label": raw.strip(), "callout": "", "style": "normal"}
    if not isinstance(raw, dict):
        return {"label": str(raw), "callout": "", "style": "normal"}
    d = dict(raw)
    style = _STYLE_MAP.get(str(d.pop("style", "normal")).lower().replace(" ", "_"), "normal")
    if not d:
        return {"label": "", "callout": "", "style": style}
    label, val = next(iter(d.items()))
    return {"label": str(label).strip(), "callout": str(val).strip() if val is not None else "", "style": style}

# ── Font registration ─────────────────────────────────────────────────────────
_FONT_FAMILIES = {
    "arial": {
        "Regular":    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "Bold":       "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "Italic":     "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        "BoldItalic": "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
        "label": "Arial (Liberation Sans)",
    },
    "dejavu": {
        "Regular":    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "Bold":       "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "Italic":     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "BoldItalic": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        "label": "DejaVu Sans",
    },
    "dejavu-condensed": {
        "Regular":    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "Bold":       "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "Italic":     "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Oblique.ttf",
        "BoldItalic": "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf",
        "label": "DejaVu Sans Condensed",
    },
    "dejavu-mono": {
        "Regular":    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "Bold":       "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "Italic":     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
        "BoldItalic": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",
        "label": "DejaVu Sans Mono",
    },
}
_FALLBACK_FONTS = {
    "Regular": "Helvetica", "Bold": "Helvetica-Bold",
    "Italic": "Helvetica-Oblique", "BoldItalic": "Helvetica-BoldOblique",
}

_family   = _FONT_FAMILIES.get(FONT_CHOICE, _FONT_FAMILIES["dejavu-condensed"])
_fonts_ok = all(os.path.isfile(_family[k]) for k in ("Regular", "Bold", "Italic", "BoldItalic"))
if _fonts_ok:
    pdfmetrics.registerFont(TTFont("F-Regular",    _family["Regular"]))
    pdfmetrics.registerFont(TTFont("F-Bold",       _family["Bold"]))
    pdfmetrics.registerFont(TTFont("F-Italic",     _family["Italic"]))
    pdfmetrics.registerFont(TTFont("F-BoldItalic", _family["BoldItalic"]))
    print(f"  Font: {_family['label']}")
else:
    print(f"  Font: Helvetica fallback ({FONT_CHOICE} TTF not found)")

FONT_NORMAL   = "F-Regular"    if _fonts_ok else _FALLBACK_FONTS["Regular"]
FONT_BOLD     = "F-Bold"       if _fonts_ok else _FALLBACK_FONTS["Bold"]
FONT_ITALIC   = "F-Italic"     if _fonts_ok else _FALLBACK_FONTS["Italic"]
FONT_BOLDITAL = "F-BoldItalic" if _fonts_ok else _FALLBACK_FONTS["BoldItalic"]

# ── Page geometry ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = landscape(A4)
CONTENT_W      = PAGE_W - 2 * OUTER_MARGIN
_n_gaps        = (_left_cols - 1) + (_right_cols - 1)
COL_W          = (CONTENT_W - _n_gaps * COL_GAP - 2 * FOLD_MARGIN) / N_COLS

def col_x(col_idx):
    """Left edge of 1-indexed physical column."""
    x = OUTER_MARGIN + (col_idx - 1) * COL_W
    gaps_before = min(col_idx - 1, _left_cols - 1)
    x += gaps_before * COL_GAP
    if col_idx > _left_cols:
        x += 2 * FOLD_MARGIN
        x += (col_idx - _left_cols - 1) * COL_GAP
    return x

CELL_PAD_X = 1.2 * mm

# ── Typography ────────────────────────────────────────────────────────────────
SIZE_HEADER   = 6.0  * SCALE
SIZE_ITEM     = 6.0 * SCALE
SIZE_NOTE     = 4.8  * SCALE
SIZE_TITLE    = 9.0  * SCALE
SIZE_SUBTITLE = 6.0  * SCALE

HDR_BAR_H = 6.0  * mm * SCALE
ITEM_LEAD = SIZE_ITEM * 0.35278 * LINE_SPACING * mm
NOTE_LEAD = SIZE_NOTE * 0.35278 * LINE_SPACING * mm
SEC_GAP   = 1.2  * mm * SCALE

# ── Colors ────────────────────────────────────────────────────────────────────
COL_HEADER_BG = colors.black
COL_EMERG_BG  = colors.HexColor("#C00000")
COL_HEADER_FG = colors.white
COL_BLUE      = colors.HexColor("#2F5496")
COL_RED       = colors.HexColor("#C00000")
COL_BLACK     = colors.black
COL_GREY      = colors.HexColor("#555555")
COL_DOTS      = colors.HexColor("#999999")
COL_BODY_GREY = colors.HexColor("#F2F2F2")  # light grey section body background

# Section header colour palette (normal procedures; prints well, harmonises with COL_BLUE)
_HDR_COLORS = {
    "black":  (colors.black,               colors.white),   # default
    "blue":   (colors.HexColor("#2F5496"), colors.white),   # same as speeds
    "green":  (colors.HexColor("#4E7A3A"), colors.white),   # mid-tone green
    "yellow": (colors.HexColor("#B8860B"), colors.white),   # dark goldenrod – warm, readable
}

def resolve_hdr_color(name):
    return _HDR_COLORS.get(str(name).lower(), _HDR_COLORS["black"])

# ── Canvas ────────────────────────────────────────────────────────────────────
c = canvas.Canvas(output_file, pagesize=landscape(A4))
_doc_title = f'{meta.get("callsign","")}  {meta.get("icao_type","")}'.strip() or meta.get("title","Checklist")
c.setTitle(_doc_title)

def tw(text, font, size):
    return pdfmetrics.stringWidth(text, font, size)

# ── Title bar ─────────────────────────────────────────────
# Layout per half (two rows):
#   Row 1 (large bold left):  CALLSIGN  ICAO_TYPE    [right small: revision]
#   Row 2 (smaller left):     model
BAR_H    = 11.0 * mm * SCALE   # taller to fit two rows
SIZE_REV = SIZE_NOTE            # small revision text

def draw_title_bar():
    y_top   = PAGE_H - OUTER_MARGIN
    left_x  = col_x(1)
    left_w  = col_x(_left_cols) + COL_W - left_x
    right_x = col_x(_left_cols + 1) if _right_cols > 0 else left_x + left_w
    right_w = col_x(N_COLS) + COL_W - right_x

    callsign  = meta.get("callsign",  "")
    icao_type = meta.get("icao_type", "")
    model     = meta.get("model",     meta.get("subtitle", ""))
    revision  = meta.get("revision",  "")
    title_str = "  ".join(filter(None, [callsign, icao_type]))

    pad = CELL_PAD_X * 2
    for x, w in [(left_x, left_w), (right_x, right_w)]:
        c.setFillColor(COL_BODY_GREY)
        c.rect(x, y_top - BAR_H, w, BAR_H, fill=1, stroke=0)
        c.setFillColor(COL_HEADER_BG)

        # Row 1: title (left) + revision (right, small)
        row1_y = y_top - BAR_H * 0.40
        c.setFont(FONT_BOLD, SIZE_TITLE)
        c.drawString(x + pad, row1_y, title_str)
        if revision:
            c.setFont(FONT_NORMAL, SIZE_REV)
            c.drawRightString(x + w - pad, row1_y, revision)

        # Row 2: model (left, smaller)
        row2_y = y_top - BAR_H * 0.78
        c.setFont(FONT_NORMAL, SIZE_SUBTITLE)
        c.drawString(x + pad, row2_y, model)

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
    items   = [parse_item(i) for i in section.get("items", [])]
    mid     = (len(items) + 1) // 2
    left    = items[:mid]
    right   = items[mid:]
    rows    = max(len(left), len(right))
    body_h  = rows * ITEM_LEAD + 1.0 * mm
    total_h = HDR_BAR_H + 0.5 * mm + body_h

    c.setFillColor(COL_BODY_GREY)  # speeds always get light-grey body
    c.rect(cx, cy - total_h, col_width, total_h, fill=1, stroke=0)
    c.setStrokeColor(COL_BLUE); c.setLineWidth(0.4)
    c.rect(cx, cy - total_h, col_width, total_h, fill=0, stroke=1)
    c.setFillColor(COL_BLUE)
    c.rect(cx, cy - HDR_BAR_H, col_width, HDR_BAR_H, fill=1, stroke=0)
    c.setFillColor(COL_HEADER_FG); c.setFont(FONT_BOLD, SIZE_HEADER)
    ty = cy - HDR_BAR_H + (HDR_BAR_H - SIZE_HEADER * 0.35278 * mm) / 2
    c.drawCentredString(cx + col_width / 2, ty, section["title"])
    cy -= HDR_BAR_H + 0.5 * mm

    half_w = col_width / 2
    c.setStrokeColor(COL_BLUE); c.setLineWidth(0.3)
    c.line(cx + half_w, cy, cx + half_w, cy - body_h + 1.0 * mm)

    def draw_speed_row(item, x, y, w):
        is_red = item["style"] == "red_bold"
        col    = COL_RED if is_red else COL_BLACK
        text_y = y - SIZE_ITEM * 0.35278 * mm
        c.setFillColor(col); c.setFont(FONT_BOLD if is_red else FONT_NORMAL, SIZE_ITEM)
        c.drawString(x + CELL_PAD_X, text_y, item["label"])
        if item["callout"]:
            c.setFillColor(col); c.setFont(FONT_BOLD, SIZE_ITEM)
            c.drawRightString(x + w - CELL_PAD_X, text_y, item["callout"])

    row_y = cy
    for item in left:
        draw_speed_row(item, cx, row_y, half_w);  row_y -= ITEM_LEAD
    row_y = cy
    for item in right:
        draw_speed_row(item, cx + half_w, row_y, half_w); row_y -= ITEM_LEAD

    return cy - body_h - SEC_GAP

# ── Section renderer ──────────────────────────────────────────────────────────
def render_section(section, cx, cy, col_width, default_type="normal"):
    sec_type = section.get("type", default_type)
    if sec_type == "speeds":
        return render_speeds(section, cx, cy, col_width)

    title  = section["title"]
    items  = [parse_item(i) for i in section.get("items", [])]
    body_h = sum(NOTE_LEAD if i["style"] == "note" else ITEM_LEAD for i in items)
    total_h = HDR_BAR_H + 0.5 * mm + body_h

    if sec_type == "emergency":
        hdr_bg, hdr_fg = COL_EMERG_BG, COL_HEADER_FG
    else:
        hdr_bg, hdr_fg = resolve_hdr_color(section.get("header_color", "black"))
    if section.get("body_bg", False):
        c.setFillColor(COL_BODY_GREY)
        c.rect(cx, cy - total_h, col_width, total_h, fill=1, stroke=0)
    c.setStrokeColor(hdr_bg); c.setLineWidth(0.4)
    c.rect(cx, cy - total_h, col_width, total_h, fill=0, stroke=1)
    c.setFillColor(hdr_bg)
    c.rect(cx, cy - HDR_BAR_H, col_width, HDR_BAR_H, fill=1, stroke=0)
    c.setFillColor(hdr_fg); c.setFont(FONT_BOLD, SIZE_HEADER)
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
Y_START     = PAGE_H - OUTER_MARGIN - BAR_H - 1 * mm

draw_title_bar()

# Render normal sections on left half
for col_data in data.get("normal", []):
    phys_col = col_data["col"]
    cx = col_x(phys_col)
    cy = Y_START
    for section in col_data.get("sections", []):
        cy = render_section(section, cx, cy, COL_W, default_type="normal")

# Render emergency sections on right half (offset by _left_cols)
for col_data in data.get("emergency", []):
    phys_col = _left_cols + col_data["col"]
    cx = col_x(phys_col)
    cy = Y_START
    for section in col_data.get("sections", []):
        cy = render_section(section, cx, cy, COL_W, default_type="emergency")

# ── Generated-by watermark (bottom-left) ─────────────────────────────────────
c.setFont(FONT_NORMAL, 4.5)
c.setFillColor(colors.HexColor("#aaaaaa"))
c.drawString(OUTER_MARGIN, OUTER_MARGIN * 0.45,
             "Generated using https://checklists.helgenberger.net/")

c.save()
print(f"✓  Generated: {output_file}")
