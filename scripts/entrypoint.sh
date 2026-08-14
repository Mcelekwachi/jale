#!/usr/bin/env bash
# Container entrypoint.
#
# Migration and seeding are OFF by default. Turn them on with RUN_MIGRATIONS=true
# and RUN_SEED=true when you want the container to bring the database up on boot
# (convenient on Render/Railway, where a separate migration step is awkward).
#
# Both steps are idempotent and guarded by a Postgres advisory lock, so running
# several replicas will not race: one applies, the rest wait and then no-op.

set -euo pipefail

: "${PORT:=8000}"
: "${RUN_MIGRATIONS:=false}"
: "${RUN_SEED:=false}"
: "${MIGRATE_ONLY:=false}"
: "${SEED_LANGUAGES:=ibo}"
: "${WEB_CONCURRENCY:=2}"

if [[ "${RUN_MIGRATIONS}" == "true" || "${RUN_SEED}" == "true" ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "entrypoint: DATABASE_URL is required for migrate/seed" >&2
    exit 1
  fi

  python - <<'PY'
import os, sys, time
import psycopg

url = os.environ["DATABASE_URL"]
LOCK_ID = 8110977            # arbitrary, stable across deploys

for attempt in range(30):    # database may still be starting
    try:
        conn = psycopg.connect(url, autocommit=True)
        break
    except Exception as exc:
        print(f"entrypoint: waiting for database ({exc.__class__.__name__})")
        time.sleep(2)
else:
    sys.exit("entrypoint: database never became reachable")

with conn:
    conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
    try:
        if os.environ.get("RUN_MIGRATIONS") == "true":
            print("entrypoint: applying db/schema.sql (idempotent)")
            with open("db/schema.sql", encoding="utf-8") as fh:
                conn.execute(fh.read())
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
PY

  if [[ "${RUN_SEED}" == "true" ]]; then
    for lang in ${SEED_LANGUAGES//,/ }; do
      echo "entrypoint: seeding ${lang}"
      python db/seed/seed.py --language "${lang}"
      if [[ "${PLACEHOLDER_AUDIO:-false}" == "true" ]]; then
        python db/seed/placeholder_audio.py --language "${lang}" \
          --engine "${PLACEHOLDER_AUDIO_ENGINE:-silence}" \
          --out-dir "${AUDIO_DIR:-/srv/audio}" \
          --url-prefix "${AUDIO_URL_PREFIX:-/audio}"
      fi
    done
  fi
fi

if [[ "${MIGRATE_ONLY}" == "true" ]]; then
  echo "entrypoint: migrate/seed complete, exiting (MIGRATE_ONLY)"
  exit 0
fi

echo "entrypoint: starting api on :${PORT}"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
