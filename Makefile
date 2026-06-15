PYTHON ?= python
SILVER_ROOT ?= sample-data-source
SYMBOLS ?= 02723.HK,02675.HK,00100.HK,02513.HK,06082.HK
PORT ?= 9021
RESEARCH_PORT ?= 9041
RESEARCH_DATA_ROOT ?= research-data

.PHONY: install build-data smoke serve serve-research test test-research smoke-strategy-api

install:
	$(PYTHON) -m pip install -r requirements.txt

build-data:
	$(PYTHON) scripts/build_sample_data.py \
		--source-silver-root "$(SILVER_ROOT)" \
		--output-root sample-data \
		--symbols "$(SYMBOLS)"

smoke:
	PYTHONPATH=mock-xtquant/src XTMOCK_SILVER_ROOT=sample-data \
		$(PYTHON) examples/read_xtdata.py

serve:
	PYTHONPATH=mock-xtquant/src:mock-feed/src XTMOCK_SILVER_ROOT=sample-data \
		MARKET_SYMBOLS="$(SYMBOLS)" \
		$(PYTHON) -m market_mock_feed.server --host 0.0.0.0 --port $(PORT)

serve-research:
	PYTHONPATH=mock-research-api/src RESEARCH_DATA_ROOT="$(RESEARCH_DATA_ROOT)" \
		$(PYTHON) -m market_research_api.server --host 0.0.0.0 --port $(RESEARCH_PORT)

test:
	PYTHONPATH=mock-xtquant/src:mock-feed/src:backend-project/src:mock-research-api/src XTMOCK_SILVER_ROOT=sample-data RESEARCH_DATA_ROOT="$(RESEARCH_DATA_ROOT)" \
		$(PYTHON) -m pytest -q

test-research:
	PYTHONPATH=mock-research-api/src RESEARCH_DATA_ROOT="$(RESEARCH_DATA_ROOT)" \
		$(PYTHON) -m pytest -q mock-research-api/tests strategy-project/tests

smoke-strategy-api:
	cd strategy-project && \
		$(PYTHON) src/download_data.py --base-url http://127.0.0.1:$(RESEARCH_PORT) --start 2026-01-01 && \
		$(PYTHON) src/build_features.py && \
		$(PYTHON) src/backtest.py
