#!/bin/bash
set -e
echo "===================================================="
echo "     Initializing database..."
python /app/db_manager.py
sleep 3
echo "     Starting main service..."
echo "===================================================="
exec "$@"
