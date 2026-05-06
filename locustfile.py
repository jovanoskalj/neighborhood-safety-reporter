import random
from locust import HttpUser, task, between


class SafetyReporterUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Perform login on startup."""
        self.username = f"user_{random.randint(1, 10000)}"
        self.password = "Pass123!"
        
        # 0. Get CSRF token
        response = self.client.get("/accounts/register/")
        csrftoken = response.cookies.get("csrftoken") or ""
        
        # 1. Register a new user
        self.client.post("/accounts/register/", {
            "username": self.username,
            "email": f"{self.username}@example.com",
            "password1": self.password,
            "password2": self.password,
            "phone": "070123456",
        }, headers={"X-CSRFToken": csrftoken})
        
        # 2. Verify
        self.client.post("/accounts/verify-email-code/", {
            "code": "111111"
        }, headers={"X-CSRFToken": csrftoken})
        
        # 3. Login
        self.client.post("/accounts/login/", {
            "username": self.username,
            "password": self.password,
        }, headers={"X-CSRFToken": csrftoken})

    @task(3)
    def view_reports(self):
        """View the list of reports."""
        self.client.get("/reports/")

    @task(2)
    def view_map(self):
        """View the interactive map."""
        self.client.get("/reports/map/")

    @task(1)
    def submit_report(self):
        """Submit a new report."""
        # Get token again for submission
        response = self.client.get("/reports/submit/")
        csrftoken = response.cookies.get("csrftoken") or ""
        
        self.client.post("/reports/submit/", {
            "description": "Load test report - pothole detected",
            "latitude": 41.9965 + random.uniform(-0.01, 0.01),
            "longitude": 21.4312 + random.uniform(-0.01, 0.01),
            "category": "infrastructure",
            "priority": "normal",
            "municipality": "centar",
        }, headers={"X-CSRFToken": csrftoken})

    @task(1)
    def view_notifications(self):
        """View user notifications."""
        self.client.get("/accounts/notifications/")
