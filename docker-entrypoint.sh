#!/usr/bin/env bash
set -e

# Wait for database availability if running in containerized environment
if [ -n "$POSTGRES_SERVER" ]; then
  echo "Waiting for PostgreSQL at ${POSTGRES_SERVER}:${POSTGRES_PORT:-5432}..."
  while ! python -c "import socket; s = socket.socket(); s.settimeout(2); s.connect(('${POSTGRES_SERVER}', int('${POSTGRES_PORT:-5432}'))); s.close()" 2>/dev/null; do
    sleep 1
  done
  echo "PostgreSQL is ready!"
fi

# Execute database migrations if container is starting web app
if [ "$1" = "uvicorn" ] || [ "$1" = "web" ]; then
  echo "Running database schema migrations with Alembic..."
  alembic upgrade head
  echo "Database schema up-to-date."
fi

exec "$@"
