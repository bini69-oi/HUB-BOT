FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic

WORKDIR /app
COPY server.py .

ENV TS_DB_PATH=/data/telemetry.db
VOLUME /data
EXPOSE 8088

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8088"]
