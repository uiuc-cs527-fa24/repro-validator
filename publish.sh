#!/usr/bin/env sh
set -ex

mypy --strict --package repro_validator
ruff format repro_validator
ruff check --fix repro_validator
version=$(python -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')
if [ "$(grep -c "${version}" README.md)" -ne 3 ]; then
    echo 'Is README.md updated to refer to the new version?'
    exit
fi
git add -A
git commit -m "Bump version to ${version}"
git tag "${version}"
git push --tags
git push
nix build '.#docker'
docker load < result
docker push "ghcr.io/charmoniumq/repro-validator:${version}"
