import os
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PRODUCTION_URL = os.environ.get(
    "PRODUCTION_URL",
    "https://neighborhood-safety-reporter.onrender.com"
).rstrip("/")

ADMIN_USERNAME = os.environ.get("SMOKE_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASS", "admin123")
CITIZEN_USERNAME = os.environ.get("SMOKE_CITIZEN_USER", "citizen")
CITIZEN_PASSWORD = os.environ.get("SMOKE_CITIZEN_PASS", "citizen123")

TIMEOUT = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_csrf_token(session, url):
    session.get(url, timeout=TIMEOUT)
    return session.cookies.get("csrftoken", "")


def login(session, username, password):
    login_url = f"{PRODUCTION_URL}/accounts/login/"
    csrf = get_csrf_token(session, login_url)
    return session.post(
        login_url,
        data={
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": login_url},
        allow_redirects=True,
        timeout=TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Site availability
# ---------------------------------------------------------------------------

def test_home_page_loads():
    response = requests.get(PRODUCTION_URL + "/", timeout=TIMEOUT)
    assert response.status_code == 200


def test_login_page_loads():
    response = requests.get(f"{PRODUCTION_URL}/accounts/login/", timeout=TIMEOUT)
    assert response.status_code == 200
    assert "csrfmiddlewaretoken" in response.text


def test_register_page_loads():
    response = requests.get(f"{PRODUCTION_URL}/accounts/register/", timeout=TIMEOUT)
    assert response.status_code == 200


def test_map_page_redirects_guests():
    response = requests.get(
        f"{PRODUCTION_URL}/reports/map/",
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert response.status_code in (301, 302)


# ---------------------------------------------------------------------------
# Authentication flows
# ---------------------------------------------------------------------------

def test_citizen_login_succeeds():
    session = requests.Session()
    response = login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    assert response.status_code == 200
    assert "/login" not in response.url


def test_admin_login_succeeds():
    session = requests.Session()
    response = login(session, ADMIN_USERNAME, ADMIN_PASSWORD)
    assert response.status_code == 200
    assert "/login" not in response.url


def test_invalid_credentials_rejected():
    session = requests.Session()
    response = login(session, "nonexistent_user_xyz", "wrongpassword")
    assert "/login" in response.url or "invalid" in response.text.lower() or \
           "невалидни" in response.text.lower()


def test_logout_clears_session():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)

    logout_url = f"{PRODUCTION_URL}/accounts/logout/"
    csrf = get_csrf_token(session, logout_url)
    session.post(
        logout_url,
        data={"csrfmiddlewaretoken": csrf},
        headers={"Referer": logout_url},
        allow_redirects=True,
        timeout=TIMEOUT,
    )

    response = session.get(
        f"{PRODUCTION_URL}/reports/map/",
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert response.status_code in (301, 302)


# ---------------------------------------------------------------------------
# Report submission
# ---------------------------------------------------------------------------

def test_submit_report_page_accessible_after_login():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/submit/", timeout=TIMEOUT)
    assert response.status_code == 200


def test_submit_report_post_with_gps():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)

    submit_url = f"{PRODUCTION_URL}/submit/"
    csrf = get_csrf_token(session, submit_url)

    response = session.post(
        submit_url,
        data={
            "description": "Smoke test report – автоматски тест",
            "latitude": "41.9981",
            "longitude": "21.4254",
            "category": "safety",
            "priority": "normal",
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": submit_url},
        allow_redirects=True,
        timeout=TIMEOUT,
    )
    assert response.status_code in (200, 302)


def test_unauthenticated_submit_redirects():
    response = requests.get(
        f"{PRODUCTION_URL}/submit/",
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert response.status_code in (301, 302)


# ---------------------------------------------------------------------------
# Map loads
# ---------------------------------------------------------------------------

def test_map_page_loads_after_login():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/reports/map/", timeout=TIMEOUT)
    assert response.status_code == 200
    assert "leaflet" in response.text.lower()


def test_reports_json_endpoint_returns_data():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/api/reports/json/", timeout=TIMEOUT)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)


def test_reports_json_contains_lat_lng():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/api/reports/json/", timeout=TIMEOUT)
    results = response.json().get("results", [])
    for r in results[:5]:
        assert "lat" in r and "lng" in r


# ---------------------------------------------------------------------------
# Officer panel
# ---------------------------------------------------------------------------

def test_officer_panel_blocked_for_citizens():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/officer/", allow_redirects=True, timeout=TIMEOUT)
    assert response.status_code in (200, 302, 403)
    if response.status_code == 200:
        assert "login" in response.url or "officer" not in response.url


def test_officer_panel_accessible_for_admin():
    session = requests.Session()
    login(session, ADMIN_USERNAME, ADMIN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/officer/", allow_redirects=True, timeout=TIMEOUT)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Admin panel + export
# ---------------------------------------------------------------------------

def test_admin_dashboard_accessible():
    session = requests.Session()
    login(session, ADMIN_USERNAME, ADMIN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/dashboard/", allow_redirects=True, timeout=TIMEOUT)
    assert response.status_code == 200


def test_admin_dashboard_blocked_for_citizens():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/dashboard/", allow_redirects=True, timeout=TIMEOUT)
    assert "/dashboard" not in response.url or response.status_code in (302, 403)


def test_admin_export_csv_downloads():
    session = requests.Session()
    login(session, ADMIN_USERNAME, ADMIN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/dashboard/export/", timeout=TIMEOUT)
    assert response.status_code == 200
    content_type = response.headers.get("Content-Type", "")
    assert "csv" in content_type or "spreadsheet" in content_type or "octet-stream" in content_type
    assert "attachment" in response.headers.get("Content-Disposition", "")


def test_admin_export_blocked_for_citizens():
    session = requests.Session()
    login(session, CITIZEN_USERNAME, CITIZEN_PASSWORD)
    response = session.get(f"{PRODUCTION_URL}/dashboard/export/", allow_redirects=True, timeout=TIMEOUT)
    content_type = response.headers.get("Content-Type", "")
    assert "csv" not in content_type and "spreadsheet" not in content_type