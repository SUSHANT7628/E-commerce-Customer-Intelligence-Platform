.PHONY: install data synthetic run test lint api dashboard docker clean

install:        ## install package + dev tools
	pip install -e ".[dev]"

data:           ## download the public Olist dataset (~85 MB)
	retailpulse download

synthetic:      ## generate an offline synthetic dataset instead
	retailpulse generate

run:            ## build warehouse, train models, score customers, write reports
	retailpulse run

test:
	pytest

lint:
	ruff check src tests dashboard

api:
	retailpulse serve --host 0.0.0.0

dashboard:
	retailpulse dashboard --host 0.0.0.0

docker:
	docker compose up --build

clean:
	rm -rf artifacts .pytest_cache .ruff_cache
