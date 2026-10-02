.PHONY: install lint typecheck test check corpus baseline maps reproduce reproduce-attrs published demo clean

# Use the project venv when there is one, so `make` works without activating it.
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

install:
	$(PYTHON) -m pip install -e ".[dev,eval]"

lint:
	$(PYTHON) -m ruff check src tests eval
	$(PYTHON) -m ruff format --check src tests eval

typecheck:
	$(PYTHON) -m mypy --strict src/tia

test:
	$(PYTHON) -m pytest

check: lint typecheck test

# --- the evaluation -------------------------------------------------------
# Every published number comes from eval/results/, and eval/published.json says
# which files those are. These targets regenerate them.

corpus-%:                    ## clone one pinned repo, install it, install tia into it
	$(PYTHON) eval/corpus.py prepare --repo $*

corpus: corpus-attrs corpus-scrapy

map-%:                       ## build the map for one corpus repo, e.g. make map-attrs
	cd eval/.corpus/$*/repo && ../.venv/bin/tia build --jobs 10

maps: map-attrs map-scrapy

replay-%:                    ## replay one repo's published experiment, both arms
	$(PYTHON) eval/harness.py --repo $* --published
	$(PYTHON) eval/harness.py --repo $* --published --no-import-graph

published:                   ## print the table the README publishes
	$(PYTHON) eval/report.py

# Reproduce the published safety table. Replays the exact recorded mutations —
# not a fresh sample, because a rebuilt map shifts which sites a seed picks
# (D-0013) — with the settings each result was measured under, then checks the
# outcome against the published files.
#
# Takes about 2.5 hours on an Apple M4: attrs ~50 min (200 mutants per arm,
# serial) and scrapy ~90 min (30 per arm, but a 50-second suite).
reproduce: corpus maps replay-attrs replay-scrapy
	$(PYTHON) eval/report.py --compare

# The same, attrs only. About an hour.
reproduce-attrs: corpus-attrs map-attrs replay-attrs
	$(PYTHON) eval/report.py --compare

baseline:                    ## re-time the optimised baselines (D-0004, D-0005)
	$(PYTHON) eval/corpus.py baseline --repo attrs  --runs 5 --warmup 1
	$(PYTHON) eval/corpus.py baseline --repo scrapy --runs 5 --warmup 1
	$(PYTHON) eval/corpus.py table

demo:                        ## the review demo, on the attrs checkout
	./scripts/demo.sh

clean:                       ## remove corpus checkouts (results are kept)
	rm -rf eval/.corpus
