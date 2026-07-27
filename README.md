# Jalɛ

Jalɛ is a progressive web app for learning African languages. Phase 1 teaches Central Igbo through vocabulary, phrases, quizzes, and culturally grounded proverbs. Language packs live under `content/<iso-639-3>/`, while curriculum selection is stored as track and rule data rather than application branches.

The current repository contains the FastAPI read API, PostgreSQL schema, Igbo content pack, seed tooling, and deployment configuration. The React PWA and authenticated write paths are not yet implemented.

## Quickstart

Docker Compose starts PostgreSQL, applies the schema, seeds all 157 Igbo content items, generates placeholder audio, and then starts the API:

```bash
git clone https://github.com/CHANGE-ME/jale.git
cd jale
docker compose up --build
```

Open the interactive API documentation at <http://localhost:8000/docs>. To stop the services while preserving database data, run `docker compose down`. Running `docker compose down -v` also removes the local database and generated-audio volumes.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Process liveness check. |
| `GET` | `/health/db` | Database readiness and seeded-content counts. |
| `GET` | `/v1/languages` | List active languages; optionally include inactive languages. |
| `GET` | `/v1/languages/{code}/categories` | List non-empty categories for a language. |
| `GET` | `/v1/content` | List, filter, search, and paginate published content. |
| `GET` | `/v1/content/{item_id}` | Fetch one published content item. |
| `GET` | `/v1/tracks` | List curriculum tracks for a language. |
| `GET` | `/v1/tracks/resolve` | Resolve onboarding answers to a curriculum track. |
| `GET` | `/v1/tracks/{slug}` | Fetch a track and its units. |
| `GET` | `/v1/tracks/{slug}/units/{position}/items` | Build the flashcard, quiz, phrase-practice, or proverb session for a unit. |

## Local development

Copy `.env.example` to `.env` when running tools outside Docker, and point `DATABASE_URL` at a PostgreSQL database.

```bash
# Validate every language pack without writing to the database
python db/seed/seed.py --all --dry-run

# Re-seed the Compose database after editing content
docker compose run --rm seed

# Run the API tests against a disposable PostgreSQL database
cd backend
pytest -q

# From the repository root, lint and verify formatting
ruff check backend db
ruff format --check backend db
```

Common container tasks are also available through `make up`, `make seed`, `make test`, `make lint`, and `make logs`. Contributor seed and worklist instructions are in [`db/seed/README.md`](db/seed/README.md).

## Deployment

GitHub Actions validates content, lints the Python code, runs the PostgreSQL-backed API tests, and builds the backend image. The release workflow publishes successful main-branch and tagged builds to GitHub Container Registry at `ghcr.io/<owner>/<repository>/api`.

`render.yaml` provisions PostgreSQL and the API on Render using that image. Replace its `CHANGE-ME` image owner and set `CORS_ORIGINS` to the deployed frontend origins. The release workflow can trigger Render or Railway when `RENDER_DEPLOY_HOOK` or `RAILWAY_DEPLOY_HOOK` is configured as a repository secret; otherwise it publishes the image without triggering a host deployment.
