#!/bin/bash
set -e

git pull

docker compose build api
docker compose up -d

echo "Done. API restarted with latest changes."
