PYTHON := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)

.PHONY: up down seed eval test reset lint

up:
	docker compose up --build -d
	@echo "Services starting..."
	@echo "FastAPI docs: http://localhost:8000/docs"
	@echo "Streamlit UI: http://localhost:8501"

down:
	docker compose down

seed:
	@echo "Seeding database..."
	$(PYTHON) db/seed.py

eval:
	@echo "Running evaluation suite..."
	$(PYTHON) eval/run_evals.py
	@echo "Results written to eval/results/latest_results.md"

test:
	@echo "Running unit tests..."
	$(PYTHON) -m pytest tests/ -v --tb=short

reset:
	docker compose down -v
	docker compose up --build -d
	@sleep 5
	$(PYTHON) db/seed.py

lint:
	ruff check app/ tests/ eval/ ui/ --fix
