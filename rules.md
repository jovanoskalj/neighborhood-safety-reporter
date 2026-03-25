---
description: Neighborhood Safety Reporter – full project implementation rules for MK31
globs: ["**/*.py", "**/*.html", "**/*.js", "**/*.css", "**/*.yml", "**/*.env*", "**/Dockerfile*"]
alwaysApply: true
---

# Neighborhood Safety Reporter – Cursor Implementation Rules

## 1. PROJECT OVERVIEW

Build a Django web application called **Neighborhood Safety Reporter** for the Smart & Safe City domain.
Citizens report urban problems; AI auto-classifies them and routes them to the correct municipal sector.
Three user roles: **Citizen**, **Officer** (sector employee), **Administrator**.

---

## 2. TECH STACK (non-negotiable)

| Layer | Technology |
|---|---|
| Backend | Django 4.x (Python 3.11+) |
| Frontend | Django Templates + Bootstrap 5 |
| Maps | Leaflet.js + OpenStreetMap (NO Google Maps) |
| Database | PostgreSQL |
| AI/ML | Ollama (local LLM, llama3 or mistral) |
| Email | SendGrid API  |
| DevOps | Docker + Docker Compose |
| Hosting | Render (cloud) |
| Version Control | Git + GitHub |
| Charts | Chart.js |
| Data Export | CSV + openpyxl (Excel) |

---

## 3. PROJECT STRUCTURE

```
neighborhood_safety_reporter/
├── .cursor/
│   └── rules/
├── config/                  # Django project settings
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/            # User auth, roles, profiles
│   ├── reports/             # Report submission & management
│   ├── notifications/       # Email notifications (SendGrid)
│   ├── ai_classifier/       # Ollama AI classification
│   ├── analytics/           # Dashboard, charts, export
│   └── maps/                # Leaflet map views
├── templates/
│   ├── base.html
│   ├── accounts/
│   ├── reports/
│   ├── analytics/
│   └── maps/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
├── media/                   # Uploaded images
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── manage.py
```

---

## 4. DATA MODELS

### Report (apps/reports/models.py)
```python
class Report(models.Model):
    STATUS_CHOICES = [('new', 'New'), ('in_progress', 'In Progress'), ('resolved', 'Resolved'), ('unclassified', 'Unclassified')]
    PRIORITY_CHOICES = [('urgent', 'Urgent'), ('normal', 'Normal'), ('low', 'Low')]
    CATEGORY_CHOICES = [('infrastructure', 'Infrastructure'), ('utilities', 'Utilities'), ('safety', 'Safety'), ('health', 'Health'), ('other', 'Other')]
    SECTOR_CHOICES = [('infrastructure', 'Infrastructure'), ('utilities', 'Utilities'), ('safety', 'Safety'), ('health', 'Health'), ('admin', 'Administration')]

    citizen = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    description = models.TextField()
    image = models.ImageField(upload_to='reports/', blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, default='admin')
    assigned_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_reports')
    internal_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    ai_processed = models.BooleanField(default=False)
```

### UserProfile (apps/accounts/models.py)
```python
class UserProfile(models.Model):
    ROLE_CHOICES = [('citizen', 'Citizen'), ('officer', 'Officer'), ('admin', 'Administrator')]
    SECTOR_CHOICES = [same as Report.SECTOR_CHOICES]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, blank=True)  # only for officers
    phone = models.CharField(max_length=20, blank=True)
```

### AuditLog (apps/accounts/models.py)
```python
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    target_model = models.CharField(max_length=100)
    target_id = models.IntegerField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)
```

---

## 5. FUNCTIONAL REQUIREMENTS (implement ALL of these)

### FR-01 to FR-05: User Management
- [ ] FR-01: Citizen registration with email + password; send verification email using `django-verify-email`
- [ ] FR-02: Login/logout using Django sessions; support JWT as optional
- [ ] FR-03: Three roles: Citizen, Officer, Administrator — enforced via Django Groups & Permissions
- [ ] FR-04: Admin panel for activating/deactivating accounts and assigning roles
- [ ] FR-05: Profile page — change password and personal info via Django forms

### FR-06 to FR-13: Report Submission & Management
- [ ] FR-06: Citizen submits report with text description (required field)
- [ ] FR-07: GPS location via Leaflet.js map click OR browser Geolocation API (auto-detect button)
- [ ] FR-08: Optional image upload (jpg/png), stored in /media/reports/
- [ ] FR-09: AI auto-classifies report → category + priority using Ollama (see Section 7)
- [ ] FR-10: System auto-routes report to correct sector based on AI output
- [ ] FR-11: Officer views and updates only reports in their sector (enforce with Django permissions)
- [ ] FR-12: Status field: New → In Progress → Resolved (with timestamp on each change)
- [ ] FR-13: Citizen can see status of their own reports in "My Reports" view

### FR-14 to FR-16: Notifications
- [ ] FR-14: Email notification on every status change (SendGrid API)
- [ ] FR-15: Email confirmation on successful report submission
- [ ] FR-16: (Low priority) Bulk notifications for resolved issues in region — implement as Django management command

### FR-17 to FR-20: Map & Visualization
- [ ] FR-17: Display all reports on interactive Leaflet.js + OpenStreetMap map
- [ ] FR-18: Map filters by category, status, sector — AJAX-powered (no full page reload)
- [ ] FR-19: (Medium priority) Heatmap using Leaflet.heat plugin
- [ ] FR-20: Click on map marker opens report detail popup (Bootstrap modal or Leaflet popup)

### FR-21 to FR-24: Analytics & Reports
- [ ] FR-21: Admin dashboard with Chart.js: total reports, by category, by status
- [ ] FR-22: Export reports to CSV and Excel (openpyxl), with date range filter
- [ ] FR-23: Import reports from CSV/Excel via Django management command
- [ ] FR-24: Charts filtered by time period: weekly / monthly / yearly

### FR-25 to FR-28: SendGrid Integration
- [ ] FR-25: All emails sent via SendGrid API (`sendgrid` Python package)
- [ ] FR-26: Failed email attempts are saved to DB and retried (simple retry mechanism or Celery task)
- [ ] FR-27: SendGrid API key stored in environment variables ONLY — never hardcoded
- [ ] FR-28: HTML + plain-text email templates using Django templates

---

## 6. ENVIRONMENT VARIABLES (.env)

Never hardcode secrets. Always use environment variables. Create `.env.example`:

```env
# Django
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/safety_reporter

# SendGrid
SENDGRID_API_KEY=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Media
MEDIA_ROOT=/app/media
```

---

## 7. AI CLASSIFICATION MODULE (apps/ai_classifier/)

Implement `classify_report(description: str) -> dict` that:
1. Sends the report description to Ollama via HTTP POST to `OLLAMA_BASE_URL/api/generate`
2. Prompt must ask for JSON response with fields: `category`, `priority`, `sector`
3. If Ollama call fails or returns unparseable response → set status to `unclassified`, flag for admin review
4. Cache results to avoid re-classifying the same description

```python
# Example prompt template
CLASSIFICATION_PROMPT = """
You are a municipal issue classifier. Given a citizen complaint, return ONLY valid JSON:
{{
  "category": "infrastructure|utilities|safety|health|other",
  "priority": "urgent|normal|low",
  "sector": "infrastructure|utilities|safety|health|admin"
}}

Complaint: {description}
"""
```

---

## 8. AUTHENTICATION & PERMISSIONS

Use Django's built-in Groups and Permissions system:

```python
# Permission checks
@login_required
@permission_required('reports.view_report')
def report_detail(request, pk): ...

# Officer can only see their sector
def get_queryset(self):
    if request.user.profile.role == 'officer':
        return Report.objects.filter(sector=request.user.profile.sector)
    return Report.objects.all()
```

Create three Django Groups on `post_migrate` signal: `citizens`, `officers`, `administrators`

---

## 9. DOCKER SETUP

### docker-compose.yml
```yaml
version: '3.9'
services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
      - ollama

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: safety_reporter
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  postgres_data:
  ollama_data:
```

---

## 10. URL STRUCTURE

```python
# config/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.reports.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('map/', include('apps.maps.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('api/', include('apps.reports.api_urls')),   # AJAX endpoints
]

# Key routes:
# GET  /                         → Home / map view
# GET  /reports/                 → List reports (filtered)
# GET  /reports/new/             → Submit report form
# POST /reports/new/             → Submit report (+ trigger AI)
# GET  /reports/<id>/            → Report detail
# POST /reports/<id>/status/     → Update status (officer only)
# GET  /my-reports/              → Citizen's own reports
# GET  /map/                     → Interactive map
# GET  /analytics/               → Admin dashboard
# GET  /api/reports/json/        → JSON endpoint for AJAX map
```

---

## 11. EMAIL TEMPLATES

Create HTML + text versions for:
- `notifications/email/report_submitted.html` — confirmation to citizen
- `notifications/email/status_changed.html` — status update to citizen
- `notifications/email/verification.html` — email verification

All templates use Django template variables: `{{ report.id }}`, `{{ report.status }}`, `{{ citizen.first_name }}`, etc.

---

## 12. LEAFLET MAP IMPLEMENTATION

```javascript
// static/js/map.js
const map = L.map('map').setView([41.9981, 21.4254], 13); // Default: Skopje

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

// Load reports via AJAX
fetch('/api/reports/json/')
  .then(r => r.json())
  .then(data => {
    data.forEach(report => {
      const marker = L.marker([report.lat, report.lng])
        .addTo(map)
        .bindPopup(`<b>${report.category}</b><br>${report.description}<br>Status: ${report.status}`);
    });
  });

// GPS auto-detect button
document.getElementById('gps-btn').addEventListener('click', () => {
  navigator.geolocation.getCurrentPosition(pos => {
    document.getElementById('latitude').value = pos.coords.latitude;
    document.getElementById('longitude').value = pos.coords.longitude;
    map.setView([pos.coords.latitude, pos.coords.longitude], 16);
  });
});
```

---

## 13. NON-FUNCTIONAL REQUIREMENTS (enforce in code)

| Requirement | Implementation |
|---|---|
| Page load < 3s (50 concurrent users) | Use `select_related`/`prefetch_related` on all querysets; add DB indexes on `status`, `sector`, `category` |
| Report processing < 2s | Async Ollama call (use `threading` or `celery` if needed); timeout after 5s |
| User data encryption | Use PostgreSQL with SSL; encrypt sensitive fields with `django-encrypted-model-fields` if needed |
| Access control | Every view decorated with `@login_required` + role check |
| Audit logging | Log all admin/officer actions via `AuditLog` model using Django signals |
| Mobile responsive | Bootstrap 5 grid; test all forms on 375px viewport |
| Support 1000+ reports | Paginate all list views (20 per page); add DB indexes |
| Code documentation | Every function/class must have a docstring |
| Backup-friendly | Use `DATABASE_URL` env var; provide `backup.sh` script |

---

## 14. CODING STANDARDS

- **Python**: Follow PEP8; use type hints on all function signatures
- **Django**: Use class-based views (CBVs) where possible; function-based views (FBVs) for simple cases
- **Templates**: Use `{% block %}` inheritance from `base.html`; no inline styles
- **JavaScript**: Vanilla JS only (no jQuery unless Bootstrap requires it)
- **CSS**: Use Bootstrap 5 utility classes; custom CSS in `static/css/main.css` only
- **Security**: `{% csrf_token %}` on every form; `SECURE_BROWSER_XSS_FILTER = True` in production settings
- **Error handling**: All API calls (Ollama, SendGrid) wrapped in try/except with fallback behavior
- **No secrets in code**: Use `os.environ.get()` or `django-environ` for all config values

---

## 15. STEP-BY-STEP IMPLEMENTATION ORDER

Follow this order to build incrementally:

1. **Setup** — Django project structure, Docker Compose, PostgreSQL connection, `.env`
2. **Accounts app** — User model, UserProfile, registration, login/logout, email verification, roles
3. **Reports app** — Report model, submit form, list view, detail view
4. **Maps app** — Leaflet integration, GPS detect, map view, AJAX JSON endpoint
5. **AI Classifier** — Ollama integration, auto-classify on report submit, fallback to unclassified
6. **Notifications** — SendGrid setup, email on submit + status change, retry mechanism
7. **Officer views** — Sector-filtered report list, status update, internal notes
8. **Admin dashboard** — Analytics, Chart.js charts, export CSV/Excel
9. **Polish** — Heatmap, bulk notifications, import command, audit logs
10. **Deploy** — Production settings, static files, Render config

---

## 16. RENDER DEPLOYMENT CHECKLIST

- `requirements.txt` must include: `gunicorn`, `psycopg2-binary`, `whitenoise`
- `Procfile`: `web: gunicorn config.wsgi:application`
- `DJANGO_SETTINGS_MODULE=config.settings.production` in Render env vars
- `STATIC_ROOT` configured; run `collectstatic` in build command
- `DATABASE_URL` set from Render PostgreSQL addon
- `DEBUG=False` in production

---

## 17. TESTING

- Write at least one unit test per model and one per view
- Test AI classifier with mocked Ollama responses
- Test email sending with Django's `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` in dev
- Test map JSON endpoint returns correct GeoJSON-like format

---

*This rules file was generated for Team MK31, Subject: ICT Project Management, March 2026.*
