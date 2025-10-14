#!/bin/bash

# Exit on any error
set -e

echo "Installing bertopic..."
pip install bertopic

echo "Starting Celery worker..."
celery -A audio_processing worker --loglevel=info