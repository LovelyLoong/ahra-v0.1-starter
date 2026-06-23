PYTHON ?= python

.PHONY: test lint check demo

lint:
	$(PYTHON) scripts/check.py --lint

test:
	$(PYTHON) scripts/check.py --test

check: lint test

demo:
	PYTHONPATH=src $(PYTHON) -m ahra.demo
