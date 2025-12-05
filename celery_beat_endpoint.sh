#!/bin/bash

# Exit on any error
set -e

echo "Installing bertopic..."

echo "Starting Celery beat..."
celery -A audio_processing beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler