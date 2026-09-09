.PHONY: install run quality test lint clean

install:
	python -m pip install -e ".[dev]"

run:
	python -m data_pipeline run --days 14

quality:
	python -m data_pipeline quality

test:
	pytest

lint:
	ruff check src tests

clean:
	python -m data_pipeline clean

