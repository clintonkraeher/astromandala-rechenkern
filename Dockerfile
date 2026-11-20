# syntax=docker/dockerfile:1
# Astromandala Rechenkern. Laeuft ohne ausgehendes Netz und mit schreibgeschuetztem Dateisystem.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LIBEPHEMERIS_DATA_DIR=/daten LIBEPHEMERIS_NETWORK_POLICY=sealed LIBEPHEMERIS_MODE=leb \
    LIBEPHEMERIS_PRECISION=base LIBEPHEMERIS_AUTO_SPK=0
WORKDIR /kern

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home kern \
    && mkdir -p /daten/leb

# Datendateien der Bibliothek, fest mit Pruefsumme. Stimmt sie nicht, bricht der Bau ab; der Kern
# prueft dieselben Summen noch einmal bei jedem Start.
ADD --checksum=sha256:b891de02f82b68346046da67389fd3713aa81ab299287c632cb20cc396397964 --chmod=444 \
    https://github.com/g-battaglia/libephemeris/releases/download/data-v4/base_core.leb2 /daten/leb/base_core.leb2
ADD --checksum=sha256:9364f821f09076db3cd3cfc428379e136a0eea80917af692681be405601652d8 --chmod=444 \
    https://github.com/g-battaglia/libephemeris/releases/download/data-v4/base_asteroids.leb2 /daten/leb/base_asteroids.leb2

COPY kern.py LICENSE LIZENZEN-DRITTER.md README.md ./
COPY tests/ ./tests/

# Commit der gebauten Fassung, sichtbar unter /quelle.
ARG COMMIT=unbekannt
ENV KERN_COMMIT=$COMMIT

USER kern
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
# Ein Faden je Prozess: Die Bibliothek haelt ihren Zustand je Prozess. Gunicorn legt seine
# Arbeitsdateien nach /dev/shm und oeffnet keinen Steuer-Socket, damit das Dateisystem
# schreibgeschuetzt bleiben kann.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "1", "--timeout", "30", "--worker-tmp-dir", "/dev/shm", "--no-control-socket", "--error-logfile", "-", "kern:application"]
