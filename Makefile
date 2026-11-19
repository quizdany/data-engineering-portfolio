.PHONY: install run quality catalog catalog-check publish test lint clean

install:
	python -m pip install -e ".[dev]"

run:
	python -m data_pipeline run --days 14

quality:
	python -m data_pipeline quality

catalog:
	python -m data_pipeline catalog

catalog-check:
	python -m data_pipeline catalog --check

publish:
	python -m data_pipeline publish

test:
	pytest

lint:
	ruff check src tests

clean:
	python -m data_pipeline clean

