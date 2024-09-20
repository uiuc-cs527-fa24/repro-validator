#!/usr/bin/env sh

git tag $(cat version)
git push --tags
nix build '.#docker'
docker load < result
docker push ghcr.io/uiuc-cs527-fa24/mp2-validator:$(cat version)
