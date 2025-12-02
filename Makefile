.PHONY: init
init: clean
	@echo "Setting up the virtual environment and installing dependencies..."
	python -m venv .venv
	. .venv/bin/activate; \
	pip install uv; \
	uv pip install -e ".[dev]"

.PHONY: lint
lint:
	. .venv/bin/activate; \
	ruff check src/ tests/; \
	mypy src/ --python-version 3.11 --ignore-missing-imports

.PHONY: format
format:
	. .venv/bin/activate; \
	ruff check --fix src/ tests/; \
	ruff format src/ tests/

.PHONY: test
test:
	. .venv/bin/activate; \
	PYTHONPATH=src/ coverage run -m pytest tests/ -v; \
	coverage report; \
	coverage html --directory target/coverage

.PHONY: security
security:
	@echo "Running security scans..."
	. .venv/bin/activate; \
	pip install bandit; \
	bandit -r src/ -f screen

.PHONY: build
build: lint test security
	. .venv/bin/activate; \
	python -m build

.PHONY: run
run:
	. .venv/bin/activate; \
	uvicorn deployment_queue.main:app --reload

.PHONY: docker-build
docker-build:
	docker-compose build

.PHONY: docker-run
docker-run:
	docker-compose up

.PHONY: clean
clean:
	@echo "Cleaning up virtual environment, build artifacts and caches..."
	rm -rf .venv/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf build/ dist/ *.egg-info/ target/
