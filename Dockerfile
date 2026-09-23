FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin kb
COPY app ./app
COPY seed/legacy-seed.sqlite3 ./legacy-seed.sqlite3
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
