.PHONY: up down seed eval test reset lint

up:
	docker-compose up --build -d
	@echo "Services starting..."
	@echo "FastAPI docs: http://localhost:8000/docs"
	@echo "Streamlit UI: http://localhost:8501"

down:
	docker-compose down

seed:
	@echo "Seeding database..."
	python db/seed.py

eval:
	@echo "Running evaluation suite..."
	python eval/run_evals.py
	@echo "Results written to eval/results/latest_results.md"

test:
	@echo "Running unit tests..."
	pytest tests/ -v --tb=short

reset:
	docker-compose down -v
	docker-compose up --build -d
	@sleep 5
	python db/seed.py

lint:
	ruff check app/ tests/ eval/ ui/ --fix
