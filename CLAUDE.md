# Retyped Processing

Django backend for Retyped, a podcast discovery platform: REST API, admin, RSS feed ingest, transcription and LLM processing run as Celery tasks. The frontend is [`nuwaves/retyped_frontend`](https://github.com/nuwaves/retyped_frontend).

## Stack

- Python 3.11 (CI and Dockerfile), Django 5.2, Django REST Framework, django-filter, django-cors-headers
- Celery 5 + django-celery-beat; Redis is optional (`CELERY_BROKER_URL`, `REDIS_URL`); SQS is used when no broker URL is set
- PostgreSQL (psycopg2), django-oauth-toolkit and social-auth-app-django for auth, feedparser for RSS, Groq/Whisper/AWS for transcription and LLM calls
- Lint/format: ruff (config in `pyproject.toml`)
- Single app: `audio_processing/` (models/, views/, serializers/, tasks/, signals/, admin/, tests/, migrations/)

## Commands

```bash
pip install -r requirements.txt
ruff check .                     # CI pins ruff==0.16.10
ruff format --check .            # CI check; `ruff format .` rewrites files
python manage.py test --verbosity=2 --keepdb audio_processing/tests   # what CI runs
python manage.py test audio_processing.tests.test_podcast             # one module (Django test runner)
python manage.py makemigrations --check --dry-run                     # verify: not run in CI
DJANGO_SETTINGS_MODULE=audio_processing.settings.dev python manage.py migrate
DJANGO_SETTINGS_MODULE=audio_processing.settings.dev python manage.py seed
DJANGO_SETTINGS_MODULE=audio_processing.settings.dev python manage.py runserver
celery -A audio_processing worker
```

Tests use the Django test runner (`manage.py test`); pytest is not in `requirements.txt`. CI test env: `DJANGO_SETTINGS_MODULE=audio_processing.settings.dev`, `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `DB_NAME`, Postgres 15.

Local setup: copy `.env.example` to `.env.dev` and fill it in (`docker-compose.yml` also reads `.env.dev`). It needs a Postgres server (compose has a `db` service).

## Code style

- Ruff rules `E, W, F, I, UP, DJ`, double quotes, target py311. `E501` and `DJ001` are ignored.
- Run `ruff check .` and `ruff format --check .` before pushing; CI runs both (`lint.yml`) on every push.
- Settings live in `audio_processing/settings/` (`base.py`, `dev.py`, `prod.py`). A `settings.py` file also exists next to the package (verify which one is used before editing settings).
- Management commands are in `audio_processing/management/commands/`; Celery tasks in `audio_processing/tasks/`.

## Branches and deployment

- `main` is the default branch. **Every push to `main` deploys to production**: `.github/workflows/deploy.yml` runs lint and tests, builds and pushes a GHCR image, then deploys to the Hetzner server over Tailscale. The container entrypoint runs `python manage.py migrate` on boot (`entrypoint.sh`), so migrations ship with the deploy.
- Work on a branch and open a PR into `main`. Tests run on branch pushes and PRs to `main`.
- Never push to `main` directly. Never commit `.env*` files or secrets.

## Ask before changing

These areas are high-risk. Ask the maintainer before editing them:

- Podcast ownership claims: `models/podcast_claim.py`, `models/podcast_owner.py`, `models/claim_verification.py`, `signals/podcast_claim.py`, `views/podcast_claims_viewsets.py`, `views/claim_verification_viewsets.py`, `templates/emails/claim_verification.*`
- Feed ingest: `tasks/podcast_tasks.py` (`process_podcast_rss_feed`, `process_all_active_podcasts`), `views/feed_viewsets.py`, `chart_import.py`
- Auth: `views/auth_views.py`, `auth_urls.py`, OAuth/social-auth settings in `settings/base.py`, tests `test_auth_backends.py`, `test_convert_token.py`, `test_security.py`
- Migrations (`audio_processing/migrations/`): never edit or delete an applied migration; add a new one and flag it in the PR
- Deploy and infra: `.github/workflows/*`, `Dockerfile`, `entrypoint.sh`, `celery_*_endpoint.sh`, `deploy/`

## Gotchas

- `README.md` says Postgres must be run locally and mentions seeded admin credentials; do not reuse those anywhere real.
- Both `audio_processing/celery.py` and `audio_processing/audio_processing/celery.py` exist (verify which is live before editing).
