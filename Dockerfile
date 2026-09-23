# Multi-stage build for Python API + TypeScript frontend
FROM node:20-alpine AS frontend
WORKDIR /app
COPY app/static/src ./app/static/src
COPY tsconfig.json ./
RUN npm install -g typescript && tsc --target ES2020 --module ES2020 --lib ES2020,DOM --outDir app/static/dist --allowJs --noEmitOnError false

FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin kb
COPY app ./app
COPY seed/legacy-seed.sqlite3 ./legacy-seed.sqlite3
COPY --from=frontend /app/app/static/dist ./app/static/dist
USER 10001:10001
EXPOSE 8000 8001
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1
CMD ["python", "-m", "app.main"]
