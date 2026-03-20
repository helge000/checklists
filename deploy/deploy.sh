#!/bin/bash
set -e
cd "$(dirname $0)/.."

git reset --hard
git fetch --all
git checkout origin/main

CONTAINER=$(docker ps --filter 'name=checklist' --filter 'status=running' \
  --format '{{.Names}}' | grep -v webhook | head -1)
docker restart "$CONTAINER"
