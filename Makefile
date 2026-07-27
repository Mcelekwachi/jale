.PHONY: up down seed test lint fmt validate logs psql

up:            ## start db + api on :8000
	docker compose up --build

down:          ## stop and wipe the database
	docker compose down -v

seed:          ## re-seed after editing content/*.csv
	docker compose run --rm seed

validate:      ## validate content without a database
	python db/seed/seed.py --all --dry-run

test:          ## run the api suite (needs DATABASE_URL)
	cd backend && pytest -q

lint:
	ruff check backend db

fmt:
	ruff format backend db

logs:
	docker compose logs -f api

psql:
	docker compose exec db psql -U jale -d jale
