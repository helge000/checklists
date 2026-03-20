#!/usr/bin/env python3
"""
Checklist PDF Generator – HTTP Backend
=======================================
Wraps generate.py as a REST service.

Endpoints
---------
POST /generate
    Body:  YAML text (Content-Type: application/yaml  or  text/plain)
    Query params (all optional, same as generate.py CLI flags):
        scale=<float>          font size multiplier
        line_spacing=<float>   line height multiplier
        columns=<int>          total column count (2–6)
        fold=<float>           fold margin mm
        col_gap=<float>        inter-column gap mm
        outer_margin=<float>   page margin mm
        font=<str>             arial|dejavu|dejavu-condensed|dejavu-mono
        monospaced=1           shorthand for dejavu-mono
    Returns: application/pdf

GET /health
    Returns: {"status": "ok", "generator": "generate.py"}

GET / and GET /<path>
    Serves static files from ./public/
    Index: ./public/index.html
    Place checklist-ui.html as public/index.html to serve the UI.

Usage
-----
    python3 server.py                   # port 5000, serves ./public/
    python3 server.py --port 8080
    python3 server.py --host 0.0.0.0 --port 8080
    python3 server.py --public /path/to/dir  # custom static dir
    FLASK_DEBUG=1 python3 server.py     # dev mode with auto-reload

Example
-------
    curl -X POST http://localhost:5000/generate \\
         -H "Content-Type: application/yaml" \\
         --data-binary @deadx.yaml \\
         -o checklist.pdf

    curl -X POST "http://localhost:5000/generate?scale=1.2&columns=6" \\
         -H "Content-Type: application/yaml" \\
         --data-binary @deadx.yaml \\
         -o checklist.pdf
"""

import os
import sys
import argparse
import tempfile
import subprocess
import logging
from pathlib import Path

from flask import Flask, request, send_file, send_from_directory, jsonify

# ── Config ────────────────────────────────────────────────────────────────────
GENERATOR  = Path(__file__).parent / "generate.py"
PYTHON     = sys.executable
PUBLIC_DIR = Path(__file__).parent / "public"   # overridable via --public

def get_public_dir() -> Path:
    return app.config.get('PUBLIC_DIR', PUBLIC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _build_cmd(pdf_path: str, yaml_path: str) -> list[str]:
    """Build the generate.py command from request query params."""
    cmd = [PYTHON, str(GENERATOR), yaml_path, pdf_path]

    p = request.args

    if p.get("fold"):
        cmd += ["--fold", p["fold"]]
    if p.get("col_gap"):
        cmd += ["--col-gap", p["col_gap"]]
    if p.get("outer_margin"):
        cmd += ["--outer-margin", p["outer_margin"]]
    if p.get("columns"):
        cmd += ["--columns", p["columns"]]
    if p.get("font"):
        cmd += ["--font", p["font"]]
    if p.get("monospaced") in ("1", "true", "yes"):
        cmd += ["--monospaced"]
    if p.get("scale"):
        cmd += ["--scale", p["scale"]]
    if p.get("line_spacing"):
        cmd += ["--line-spacing", p["line_spacing"]]

    return cmd

# ── Routes ────────────────────────────────────────────────────────────────────
@app.post("/generate")
def generate():
    """Receive YAML, return PDF."""
    body = request.get_data()
    if not body:
        return jsonify(error="Empty request body – send YAML as request body"), 400

    with tempfile.TemporaryDirectory(prefix="checklist_") as tmp:
        yaml_path = os.path.join(tmp, "input.yaml")
        pdf_path  = os.path.join(tmp, "output.pdf")

        with open(yaml_path, "wb") as f:
            f.write(body)

        cmd = _build_cmd(pdf_path, yaml_path)
        log.info("Running: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            log.error("generate.py failed:\n%s", result.stderr)
            return jsonify(
                error="PDF generation failed",
                details=result.stderr or result.stdout,
            ), 500

        if not os.path.exists(pdf_path):
            return jsonify(error="generate.py succeeded but produced no PDF"), 500

        log.info("OK – returning PDF (%d bytes)", os.path.getsize(pdf_path))

        # Read into memory before tmp dir is cleaned up
        pdf_bytes = open(pdf_path, "rb").read()

    from io import BytesIO
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name="checklist.pdf",
    )


@app.get("/health")
def health():
    gen_ok = GENERATOR.exists()
    return jsonify(
        status="ok" if gen_ok else "degraded",
        generator=str(GENERATOR),
        generator_exists=gen_ok,
        python=PYTHON,
    ), 200 if gen_ok else 503



@app.get("/examples")
def list_examples():
    """Return a list of YAML checklists found in ./aircraft/ subdirectories."""
    aircraft_dir = Path(__file__).parent / "aircraft"
    if not aircraft_dir.is_dir():
        return jsonify([])

    results = []
    for yaml_file in sorted(aircraft_dir.rglob("*.yaml")):
        rel = yaml_file.relative_to(aircraft_dir)
        # Use parent dir as category, stem as display name
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else ""
        name     = yaml_file.stem.replace("-", " ").replace("_", " ")
        results.append({
            "path":     str(rel).replace("\\", "/"),
            "name":     name,
            "category": category,
        })
    return jsonify(results)


@app.get("/examples/<path:filepath>")
def get_example(filepath):
    """Serve a YAML file from ./aircraft/."""
    aircraft_dir = Path(__file__).parent / "aircraft"
    # Security: resolve and ensure it stays within aircraft_dir
    target = (aircraft_dir / filepath).resolve()
    if not str(target).startswith(str(aircraft_dir.resolve())):
        return jsonify(error="forbidden"), 403
    if not target.exists() or target.suffix not in (".yaml", ".yml"):
        return jsonify(error="not found"), 404
    return send_file(target, mimetype="application/yaml")


# ── Static file server ───────────────────────────────────────────────────────
@app.get("/")
def index():
    """Serve index.html from ./public/"""
    pub = get_public_dir()
    if not pub.is_dir():
        return jsonify(error=f"Static dir not found: {pub}"), 404
    return send_from_directory(pub, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    """Serve any file from ./public/ — skip API paths."""
    if filename.startswith("examples") or filename in ("health", "generate"):
        return jsonify(error="not found"), 404
    pub = get_public_dir()
    if not pub.is_dir():
        return jsonify(error=f"Static dir not found: {pub}"), 404
    return send_from_directory(pub, filename)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Checklist PDF generator HTTP backend")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default: 127.0.0.1 – use 0.0.0.0 for network)")
    ap.add_argument("--port", type=int, default=5000,
                    help="port (default: 5000)")
    ap.add_argument("--debug", action="store_true",
                    help="enable Flask debug / auto-reload")
    ap.add_argument("--public", metavar="DIR", default=None,
                    help="static files directory (default: ./public)")
    a = ap.parse_args()

    if a.public:
        app.config['PUBLIC_DIR'] = Path(a.public).resolve()
    log.info("Generator:   %s", GENERATOR)
    log.info("Static dir:  %s", app.config.get("PUBLIC_DIR", PUBLIC_DIR))
    log.info("Listening on http://%s:%d", a.host, a.port)
    app.run(host=a.host, port=a.port, debug=a.debug)
