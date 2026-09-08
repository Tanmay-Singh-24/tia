.PHONY: install lint typecheck test check corpus map demo safety reproduce clean

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

# --- the evaluation -------------------------------------------------------
# Every published number comes from these targets and lands in eval/results/.

CORPUS ?= attrs
SEED   ?= 1234
N      ?= 50

corpus:                       ## clone, install and verify the corpus repos
	python eval/corpus.py prepare --repo attrs
	python eval/corpus.py prepare --repo scrapy

baseline:                     ## optimised baselines, median of 5 runs
	python eval/corpus.py baseline --repo attrs  --runs 5 --warmup 1
	python eval/corpus.py baseline --repo scrapy --runs 5 --warmup 1
	python eval/corpus.py table

map:                          ## build the map for $(CORPUS)
	cd eval/.corpus/$(CORPUS)/repo && ../.venv/bin/tia build --jobs 10

safety:                       ## inject $(N) defects into $(CORPUS) and measure
	python eval/harness.py --repo $(CORPUS) --experiment safety \
		--n $(N) --seed $(SEED) --jobs auto

demo:                         ## the review demo, on the attrs checkout
	./scripts/demo.sh

# Regenerate every published table from the pinned corpus. Long: it prepares
# both repositories, rebuilds both maps and runs both safety experiments.
reproduce: corpus baseline
	$(MAKE) map CORPUS=attrs
	$(MAKE) safety CORPUS=attrs
	$(MAKE) map CORPUS=scrapy
	$(MAKE) safety CORPUS=scrapy
	python eval/corpus.py table
	@echo
	@echo "Results written to eval/results/. Every published number comes from"
	@echo "one of those files."

clean:                        ## remove corpus checkouts (results are kept)
	rm -rf eval/.corpus
