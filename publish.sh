#!/usr/bin/env sh
set -ex

mypy --strict main.py
ruff check main.py
git tag $(cat version)
git push --tags
nix build '.#docker'
docker load < result
docker push ghcr.io/uiuc-cs527-fa24/mp2-validator:$(cat version)
