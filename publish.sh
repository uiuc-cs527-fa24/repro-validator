#!/usr/bin/env sh
set -ex

mypy --strict main.py || true
ruff check main.py
if [ "$(grep $(cat version) README.md | wc -l)" -ne 2 ]; then
    echo 'Is README.md updated to refer to the new version?'
    exit
fi
git tag $(cat version)
git push --tags
nix build '.#docker'
docker load < result
docker push ghcr.io/charmoniumq/mp2-validator:$(cat version)
