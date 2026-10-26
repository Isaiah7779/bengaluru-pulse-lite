FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1     UV_THREADPOOL_SIZE=16

WORKDIR /app

# libexpat1: needed by osmium (gazetteer build CLI only)
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

# Files copied from a Windows/OneDrive build context can arrive read-only;
# the runtime, model-registry and evaluation directories must be writable.
RUN useradd --create-home appuser     && mkdir -p /app/runtime /app/models /app/evaluation/v2     && chown -R appuser:appuser /app     && chmod -R u+rwX /app/runtime /app/models /app/evaluation
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

# Apply migrations, then serve. Collector containers override CMD.
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
