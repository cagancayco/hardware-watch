FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 hardwarewatch \
    && useradd --uid 10001 --gid hardwarewatch --no-create-home hardwarewatch \
    && mkdir -p /app/data/uploads \
    && chown -R hardwarewatch:hardwarewatch /app/data

COPY app.py engine.py test_engine.py ./
COPY static/ ./static/

USER hardwarewatch
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/state', timeout=3).close()"

CMD ["python", "app.py", "--host", "0.0.0.0"]
