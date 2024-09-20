#!/usr/bin/env sh
set -ex

#mypy --strict main.py
ruff check main.py
#git tag $(cat version)
#git push --tags
nix build '.#docker'
docker load < result
docker push ghcr.io/charmoniumq/mp2-validator:$(cat version)
