#!/bin/bash
set -e

if [ ! -f secrets.h ]; then
    echo "secrets.h not found. Copy and fill in your values:"
    echo "  cp secrets.example.h secrets.h"
    exit 1
fi

docker compose up -d --build
