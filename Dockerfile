# ── Aviation Checklist Generator ─────────────────────────────────────────────
# Usage:
#   docker build -t checklist-generator .
#   docker run -p 5000:5000 checklist-generator
#
# Place checklist-ui.html as public/index.html next to server.py and
# it will be served at http://localhost:5000/
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────────────────────
# fonts-liberation  → Arial-compatible TTF (Liberation Sans)
# fonts-dejavu-core → DejaVu Sans / Condensed / Mono
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-liberation \
        fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root service user ─────────────────────────────────────────────────────
RUN groupadd --gid 1000 checklist \
 && useradd  --uid 1000 --gid checklist --no-create-home --shell /usr/sbin/nologin checklist

# ── App directory ─────────────────────────────────────────────────────────────
WORKDIR /app

# Install Python dependencies as root before switching user
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY generate.py  .
COPY server.py    .

# Copy static UI (optional – mount at runtime or bake in)
# Place checklist-ui.html as public/index.html before building,
# or mount a volume:  -v ./public:/app/public
COPY public/      ./public/

# Ownership
RUN chown -R checklist:checklist /app

# ── Runtime ───────────────────────────────────────────────────────────────────
USER checklist

EXPOSE 5000

# Bind to 0.0.0.0 so the port is reachable from outside the container
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "5000"]
