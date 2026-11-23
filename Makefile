.PHONY: install demo run test lint fmt docker-build docker-demo gif

install:
	python3.12 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'

demo:            ## run end-to-end with recorded extractions (no API keys)
	rm -f out/invoices.csv && .venv/bin/invoice-automation --mock

run:             ## real mode: needs ANTHROPIC_API_KEY in .env
	.venv/bin/invoice-automation

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

fmt:
	.venv/bin/ruff check --fix . && .venv/bin/ruff format .

docker-build:
	docker build -t invoice-automation .

docker-demo: docker-build
	docker run --rm invoice-automation --mock

gif:
	vhs docs/demo.tape
