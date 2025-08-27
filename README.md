# Audio Processing API

This repo contains all the of the code for the Django-based backend for Retyped.

## Pre-Requisities for Running in Dev
* You'll need a running Postgres server- I'd suggest running it locally for now, talk to Cody if you need help with this
* TODO: eventually make a Docker compose that brings up the DB as well

## Quickstart

The included .env.example should give you a guide to how to populate the secrets you'll need to run the app. Copy that to a file called .env.dev and replace the values with the real secrets you'd like to use.

Then, run migrations:
`DJANGO_SETTINGS_MODULE=audio_processing.settings.dev python manage.py migrate`

To populate a test user, a podcast, and a few tags you can do this: `DJANGO_SETTINGS_MODULE=audio_processing.settings.dev python manage.py seed`

Then, start the server: `DJANGO_SETTINGS_MODULE=audio_processing.settings.dev python manage.py runserver`

Point a browser to: http://localhost:8000/admin/audio_processing/tag/. You should be able to login with "admin" and "admin123" and see some test tags. 

## Running a Celery Worker

Much of the data-processing workload in the app is implemented as async tasks that will be performed by a Celery worker.

To run a worker locally, run `celery -A audio_processing worker`