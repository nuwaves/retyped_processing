#!/bin/bash

# Exit on any error
set -e

echo "Starting Django application..."

# Run database migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files (for production)
echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "Static files collection failed, proceeding..."

# Start the application
echo "Starting Django server..."
python manage.py runserver 0.0.0.0:8000