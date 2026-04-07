# Neighborhood Safety Reporter

Modern Django platform for reporting neighborhood/community issues, with role-based access, email verification via 6-digit code, and Dockerized development.

## Features

- Django 4.2 app with modular structure (`accounts`, `reports`, `analytics`, `notifications`, `ai_classifier`)
- Registration + email verification code flow (6 digits, expiring token)
- Role-aware navigation and access (`citizen`, `officer`, `admin`, `superuser`)
- Login-protected report submit route
- SendGrid support for real email delivery
- Docker Compose stack (Web + Postgres + Ollama)
- Pytest test suite

## Tech Stack

- Python 3.11
- Django 4.2
- PostgreSQL 16
- Docker / Docker Compose
- Pytest + pytest-django

## Project Structure (important parts)

- `apps/accounts/` – auth, registration, verification, profile
- `apps/reports/` – home, dashboard, submit-report entry point
- `templates/` – UI templates (base + accounts + reports)
- `config/settings.py` – app config, DB, email, middleware, installed apps
- `docker-compose.yml` – local services orchestration

## Quick Start (Docker)

1. Copy env file:

	 - `cp .env.example .env`

2. Start services:

	 - `docker compose up -d`

3. Open app:

	 - http://localhost:8000

> Note: `web` service auto-runs migrations on startup.

## Create Superuser

Run inside container:

- `docker compose exec web python manage.py createsuperuser`

Then login at:

- http://localhost:8000/accounts/login/

Admin site:

- http://localhost:8000/admin/

## Email Verification Flow

When a user registers:

1. Account is created with `is_active=False`
2. 6-digit verification code is generated
3. Code is stored with expiry
4. Email is sent to user
5. User enters code on verification page
6. Account is activated on valid code

Relevant files:

- `apps/accounts/views.py`
- `apps/accounts/models.py`
- `templates/accounts/verification_email.html`
- `templates/accounts/verify_code.html`

## SendGrid Setup

For local testing, `.env.example` defaults to console backend.

To use real SendGrid delivery, set in `.env`:

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST=smtp.sendgrid.net`
- `EMAIL_PORT=587`
- `EMAIL_USE_TLS=True`
- `EMAIL_HOST_USER=apikey`
- `SENDGRID_API_KEY=...`
- `DEFAULT_FROM_EMAIL=...` (must be a verified sender/domain in SendGrid)

## Run Tests

All tests:

- `pytest .`

Common subsets:

- `pytest tests/test_auth.py -q`
- `pytest tests/test_navbar.py -q`
- `pytest tests/test_submit_report_access.py -q`

## PGAdmin Connection (Local)

If using pgAdmin desktop app:

- Host: `localhost`
- Port: `5433`
- DB: `safety_reporter`
- User: `postgres`
- Password: `postgres`

If pgAdmin is inside Docker network, use host `db` and port `5432`.

## Troubleshooting

- **DisallowedHost (`0.0.0.0`)**
	- Add `0.0.0.0` to `ALLOWED_HOSTS` in `.env`

- **Push rejected for workflow file (`workflow` scope)**
	- Use a PAT with `repo` + `workflow` scopes

- **Email not sending**
	- Verify sender identity in SendGrid
	- Check SMTP env values and API key

## Security Note

Never commit real secrets (`.env`, API keys, tokens). If a key is exposed, rotate/revoke immediately.