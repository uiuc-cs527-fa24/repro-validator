#!/usr/bin/env sh

nix build '.#docker'
docker load < result
docker push ghcr.io/uiuc-cs527-fa24/mp2-validator:0.1.0
