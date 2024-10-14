#!/usr/bin/env sh
set -ex

mypy --strict --package repro_validator
ruff check repro_validator
if [ "$(grep $(cat version) README.md | wc -l)" -ne 2 ]; then
    echo 'Is README.md updated to refer to the new version?'
    exit
fi
git tag $(cat version)
git push --tags
nix build '.#docker'
docker load < result
docker push ghcr.io/charmoniumq/repro-validator:$(cat version)
