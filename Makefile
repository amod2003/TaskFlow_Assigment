.PHONY: help install run worker beat test test-cov lint format migrate docker-up docker-down docker-logs clean

help:
	@echo "TaskFlow API - Developer Commands"
	@echo "=================================="
	@echo "make install      - Install Python dependencies in active virtual environment"
	@echo "make run          - Run FastAPI development server with hot-reload"
	@echo "make worker       - Run Celery background worker"
	@echo "make beat         - Run Celery Beat periodic scheduler"
	@echo "make test         - Run test suite with pytest"
	@echo "make test-cov     - Run test suite with code coverage report"
	@echo "make lint         - Check code quality with Ruff"
	@echo "make format       - Auto-format code with Ruff"
	@echo "make migrate      - Run Alembic database schema migrations"
	@echo "make docker-up    - Build and launch full stack with Docker Compose"
	@echo "make docker-down  - Stop Docker Compose stack"
	@echo "make docker-logs  - Follow Docker Compose container logs"
	@echo "make clean        - Remove Python bytecode and test cache files"

install:
	pip install --upgrade pip
	pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A app.workers.celery_app.celery_app worker --loglevel=info

beat:
	celery -A app.workers.celery_app.celery_app beat --loglevel=info

test:
	pytest tests/

test-cov:
	pytest --cov=app --cov-report=term-missing tests/

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

migrate:
	alembic upgrade head

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache .mypy_cache
