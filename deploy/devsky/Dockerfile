# Escaner TQT tras Cloudflare: HTTP plano en 8000 (sin arduino-cli)
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 TZ=America/Mexico_City \
    TQT_DB_PATH=/data/db/tqt_produccion.db TQT_EXCEL_DIR=/data/excel_mensual TQT_EXPORTS_DIR=/data/exports \
    TQT_BACKUP_DIR=/backups TQT_EN_CONTENEDOR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY templates ./templates
COPY firmware ./firmware
COPY station ./station
COPY run_server.py main.py ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
