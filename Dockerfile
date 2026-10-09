# Escaner TQT - imagen de producción (HTTPS local en 8443)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Mexico_City \
    TQT_DB_PATH=/data/db/tqt_produccion.db \
    TQT_EXCEL_DIR=/data/excel_mensual \
    TQT_EXPORTS_DIR=/data/exports

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# arduino-cli + core esp32:esp32 horneados en la imagen: compilar el firmware de R1/R2 (flasheo por USB
# desde la consola de escritorio, ver firmware/README.md) no necesita red en tiempo de ejecución.
ENV TQT_ARDUINO_CLI=/opt/arduino-cli/bin/arduino-cli \
    TQT_ARDUINO_DATA_DIR=/opt/arduino-cli/data \
    ARDUINO_DIRECTORIES_DATA=/opt/arduino-cli/data \
    ARDUINO_DIRECTORIES_DOWNLOADS=/opt/arduino-cli/data/downloads \
    ARDUINO_DIRECTORIES_USER=/opt/arduino-cli/data/user
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/arduino-cli/bin /opt/arduino-cli/data \
    && curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=/opt/arduino-cli/bin sh \
    && /opt/arduino-cli/bin/arduino-cli core update-index --additional-urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json \
    && /opt/arduino-cli/bin/arduino-cli core install esp32:esp32 --additional-urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json

# Usuario sin privilegios; /data (BD, Excel, respaldos) y /app/certs son volumenes. El chown del toolchain (varios GB)
# va ANTES de copiar la app para que quede en cache (despues del COPY se repetiria y duplicaria la capa en cada build).
RUN useradd --create-home --uid 10001 tqt \
    && mkdir -p /data/db /data/excel_mensual /data/exports /backups /app/certs \
    && chown -R tqt:tqt /data /backups /app/certs /opt/arduino-cli

COPY --chown=tqt:tqt app ./app
COPY --chown=tqt:tqt templates ./templates
COPY --chown=tqt:tqt firmware ./firmware
COPY --chown=tqt:tqt station ./station
COPY --chown=tqt:tqt run_server.py main.py ./
USER tqt

EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import ssl,urllib.request as u; c=ssl._create_unverified_context(); u.urlopen('https://127.0.0.1:8443/api/health', context=c, timeout=4)" || exit 1

CMD ["python", "run_server.py"]
