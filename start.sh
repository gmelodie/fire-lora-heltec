#!/bin/bash
set -e

if [ ! -f secrets.h ]; then
    echo "secrets.h not found. Copy secrets.example.h and fill in your values:"
    echo "  cp secrets.example.h secrets.h"
    exit 1
fi

DB_PASSWORD=$(grep -E '^#define\s+DB_PASSWORD' secrets.h | sed 's/.*"\(.*\)"/\1/')

if [ -z "$DB_PASSWORD" ]; then
    echo "DB_PASSWORD not found in secrets.h"
    exit 1
fi

export DB_PASSWORD

docker compose up -d --build

echo "Waiting for API to be ready..."
PORT=$(grep -E '^#define\s+API_PORT' secrets.h | sed 's/.*"\(.*\)"/\1/')
PORT=${PORT:-8000}

API_PASSWORD=$(grep -E '^#define\s+API_PASSWORD' secrets.h | sed 's/.*"\(.*\)"/\1/')

for i in $(seq 1 20); do
    if curl -sf "http://localhost:$PORT/readings/latest" \
        -H "X-API-Password: $API_PASSWORD" \
        > /dev/null 2>&1; then
        echo "API is up at http://localhost:$PORT"
        exit 0
    fi
    sleep 1
done

echo "API did not respond after 20s. Check logs with: docker compose logs -f api"
exit 1
