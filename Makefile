.PHONY: test lint check demo

lint:
	python scripts/check.py --lint

test:
	python scripts/check.py --test

check: lint test

demo:
	PYTHONPATH=src python -m ahra.demo
