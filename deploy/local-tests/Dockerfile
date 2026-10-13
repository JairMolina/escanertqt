FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home tqt && mkdir -p /data/db /data/excel /data/exports /data/backups /app/certs && chown -R tqt:tqt /data /app/certs
COPY --chown=tqt:tqt app ./app
COPY --chown=tqt:tqt templates ./templates
COPY --chown=tqt:tqt station ./station
COPY --chown=tqt:tqt firmware ./firmware
USER tqt
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
