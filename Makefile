.PHONY: test lint check demo

lint:
	PYTHONPATH=src python scripts/lint_contracts.py

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

check: lint test

demo:
	PYTHONPATH=src python -m ahra.demo
