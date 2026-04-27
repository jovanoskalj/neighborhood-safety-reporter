# using SendGrid's Python Library
# https://github.com/sendgrid/sendgrid-python
"""Simple SendGrid smoke test script."""

import os
from pathlib import Path

from python_http_client.exceptions import HTTPError
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "safetyreport.mk@gmail.com")
TO_EMAIL = os.getenv("TEST_TO_EMAIL", "jovanoskalj@gmail.com")
TEST_USERNAME = os.getenv("TEST_USERNAME", "jovanoskalj")
TEST_CODE = os.getenv("TEST_CODE", "052593")
TEST_EXPIRY_MINUTES = os.getenv("TEST_EXPIRY_MINUTES", "15")

html_content = f"""
<!DOCTYPE html>
<html lang="mk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Верификација</title>
    <style>
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #e2e8f0;
            margin: 0;
            padding: 0;
        }}
        .email-container {{
            max-width: 550px;
            margin: 40px auto;
            background-color: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        }}
        .nav-header {{
            background-color: #0f172a;
            padding: 40px 20px;
            text-align: center;
        }}
        .nav-header h1 {{
            color: #f8fafc;
            margin: 0;
            font-size: 24px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        .body-content {{
            padding: 40px;
            background-color: #ffffff;
            text-align: center;
        }}
        .welcome-text {{
            color: #1e293b;
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        .description {{
            color: #64748b;
            font-size: 16px;
            line-height: 1.5;
            margin-bottom: 30px;
        }}
        .code-wrapper {{
            background-color: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 25px;
            margin: 20px 0;
        }}
        .verification-code {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 42px;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: 12px;
            margin: 0;
        }}
        .timer-badge {{
            display: inline-block;
            background-color: #fee2e2;
            color: #991b1b;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 20px;
        }}
        .footer {{
            background-color: #f1f5f9;
            padding: 30px;
            text-align: center;
            font-size: 13px;
            color: #64748b;
            border-top: 1px solid #e2e8f0;
        }}
        .footer p {{
            margin: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="nav-header">
            <h1>Safety Reporter</h1>
        </div>

        <div class="body-content">
            <div class="welcome-text">Здраво, {TEST_USERNAME}</div>
            <p class="description">Ви благодариме за регистрацијата. Употребете го кодот подолу за да го верификувате вашиот профил.</p>

            <div class="code-wrapper">
                <div class="verification-code">{TEST_CODE}</div>
            </div>

            <div class="timer-badge">
                Кодот важи {TEST_EXPIRY_MINUTES} минути
            </div>
        </div>

        <div class="footer">
            <p>Доколку не ја побаравте оваа порака, некој веројатно погрешил при внесување на својот е-маил. Можете слободно да ја игнорирате.</p>
            <p style="margin-top: 20px; font-weight: bold; color: #0f172a;">&copy; 2026 Safety Reporter</p>
        </div>
    </div>
</body>
</html>
"""

def main() -> None:
    if not SENDGRID_API_KEY:
        print("SENDGRID_API_KEY is not set in the environment or .env file.")
        return

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=TO_EMAIL,
        subject="Верификација - Safety Reporter",
        html_content=html_content,
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Status: {response.status_code}")
        print("Email sent successfully.")
    except HTTPError as e:
        print(f"SendGrid HTTP error: {getattr(e, 'status_code', 'unknown')}")
        print(getattr(e, "body", str(e)))
        print(
            "Hint: 401 Unauthorized usually means invalid API key, missing key in env, "
            "or sender identity is not verified in SendGrid."
        )
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()