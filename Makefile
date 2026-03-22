sources = netbox_pdu_plugin
netbox_docker_dir = ../netbox-docker

.PHONY: test format lint unittest pre-commit clean ci

test: format lint unittest

format:
	uvx ruff check --select I --fix $(sources) tests
	uvx ruff format $(sources) tests

lint:
	uvx ruff check $(sources) tests

pre-commit:
	pre-commit run --all-files

# Run the same checks as CI (lint + Docker integration tests)
ci: lint
	docker compose -f $(netbox_docker_dir)/docker-compose.yml \
		-f $(netbox_docker_dir)/docker-compose.override.yml \
		exec -T netbox python manage.py test netbox_pdu_plugin.tests --keepdb -v 2

clean:
	rm -rf *.egg-info
	rm -rf .tox dist site
