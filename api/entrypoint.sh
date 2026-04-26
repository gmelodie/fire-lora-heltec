#!/bin/sh
exec uvicorn server:app --host 0.0.0.0 --port 8443 \
  --ssl-keyfile /certs/key.pem --ssl-certfile /certs/cert.pem
