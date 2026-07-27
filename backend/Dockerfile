# Jalɛ API
#
# Build context is the REPO ROOT, not backend/, because the image also carries
# db/schema.sql and content/ so it can migrate and seed itself as a one-off job
# on Railway or Render:
#
#   docker build -f backend/Dockerfile -t jale-api .
#
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# --- dependencies -----------------------------------------------------------
# Copied first and alone so a code change does not invalidate the pip layer.
COPY backend/requirements.txt ./requirements.txt
COPY db/seed/requirements.txt ./seed-requirements.txt
RUN pip install -r requirements.txt -r seed-requirements.txt

# --- application ------------------------------------------------------------
COPY backend/app ./app
COPY backend/pytest.ini ./pytest.ini
COPY db ./db
COPY content ./content
COPY scripts/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Never run as root. Render and Railway both honour USER.
RUN useradd --create-home --uid 10001 jale && chown -R jale:jale /srv
USER jale

# Railway and Render inject PORT; 8000 is the local default.
ENV PORT=8000
EXPOSE 8000

# curl is not in the slim image, so the healthcheck uses the interpreter we
# already have.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",8000)}/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["./entrypoint.sh"]
