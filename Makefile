.PHONY: install lint typecheck test check reproduce

install:
	python -m pip install -e ".[dev,eval]"

lint:
	ruff check src tests eval
	ruff format --check src tests eval

typecheck:
	mypy --strict src/tia

test:
	pytest

check: lint typecheck test

# Review 2 deliverable: regenerate every published table from the pinned corpus.
reproduce:
	@echo "make reproduce: not implemented yet (Review 2 deliverable)"; exit 2
