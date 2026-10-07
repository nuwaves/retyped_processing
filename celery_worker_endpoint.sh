#!/bin/bash

# Exit on any error
set -e

echo "Starting Celery worker..."
celery -A audio_processing worker --loglevel=info