#!/bin/sh
PORT=$(grep 'API_URL' /secrets.h | sed 's/.*:\([0-9]*\)".*/\1/')
exec uvicorn server:app --host 0.0.0.0 --port "$PORT" \
  --ssl-keyfile /certs/key.pem --ssl-certfile /certs/cert.pem
