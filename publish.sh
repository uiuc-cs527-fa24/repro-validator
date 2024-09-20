#!/usr/bin/env sh
set -ex

#mypy --strict main.py
ruff check main.py
git tag $(cat version)
git push --tags
if [ "$(grep $(cat version) README.md | wc -l)" -ne 2 ]; then
    echo 'Is README.md updated to refer to the new version?'
fi
nix build '.#docker'
docker load < result
docker push ghcr.io/charmoniumq/mp2-validator:$(cat version)
