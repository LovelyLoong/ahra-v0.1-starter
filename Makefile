PYTHON ?= python

.PHONY: test lint check

lint:
	$(PYTHON) scripts/check.py --lint

test:
	$(PYTHON) scripts/check.py --test

check: lint test
