"""
auth.py — Simple HttpOnly cookie auth for the DCA Dynamic dashboard.

Single shared secret (DASHBOARD_SECRET env var). No user accounts, no sessions.
Cookie persists 30 days. Same pattern as autobudget.
"""

import os

from fastapi import Request
from fastapi.responses import RedirectResponse

COOKIE_NAME = "dca_auth"
DASHBOARD_SECRET = os.environ.get("DASHBOARD_SECRET", "")

LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DCA Dynamic</title>
  <link rel="icon" type="image/svg+xml" href="/icon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: #0a0805;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .card {
      background: #110e07;
      border: 1px solid rgba(245,158,11,0.15);
      border-radius: 16px;
      padding: 40px;
      width: 100%;
      max-width: 380px;
      text-align: center;
    }
    .brand-icon {
      margin-bottom: 16px;
      display: flex;
      justify-content: center;
    }
    .brand-icon img {
      width: 56px; height: 56px; border-radius: 14px;
      box-shadow: 0 0 24px rgba(245,158,11,0.3);
    }
    .brand-name {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: 0.12em;
      color: #fef3c7;
      margin-bottom: 6px;
    }
    .brand-sub {
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.1em;
      color: #78716c;
      margin-bottom: 32px;
    }
    input {
      width: 100%;
      background: #0a0805;
      border: 1px solid rgba(245,158,11,0.2);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 14px;
      color: #fef3c7;
      font-family: inherit;
      outline: none;
      margin-bottom: 12px;
      transition: border-color 0.15s;
    }
    input:focus { border-color: rgba(245,158,11,0.5); }
    input::placeholder { color: #44403c; }
    button {
      width: 100%;
      background: linear-gradient(135deg, #f59e0b, #b45309);
      border: none;
      border-radius: 8px;
      padding: 13px;
      font-size: 14px;
      font-weight: 700;
      font-family: inherit;
      color: #0a0805;
      cursor: pointer;
      letter-spacing: 0.05em;
      transition: opacity 0.15s;
    }
    button:hover { opacity: 0.9; }
    .error {
      font-size: 12px;
      color: #f87171;
      margin-top: 10px;
      min-height: 18px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="brand-icon"><img src="/icon.svg" alt="DCA Dynamic"></div>
    <div class="brand-name">DCA DYNAMIC</div>
    <div class="brand-sub">AUTOMATED WEALTH ENGINE</div>
    <input type="password" id="secret" placeholder="Access key" autocomplete="current-password"/>
    <button onclick="login()">Enter</button>
    <div class="error" id="err"></div>
  </div>
  <script>
    document.getElementById('secret').addEventListener('keydown', e => {
      if (e.key === 'Enter') login();
    });
    async function login() {
      const secret = document.getElementById('secret').value;
      const res = await fetch('/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ secret }),
      });
      if (res.ok) {
        window.location.href = '/dashboard-home';
      } else {
        document.getElementById('err').textContent = 'Invalid access key.';
        document.getElementById('secret').value = '';
        document.getElementById('secret').focus();
      }
    }
  </script>
</body>
</html>"""


def is_authenticated(request: Request) -> bool:
    if not DASHBOARD_SECRET:
        return True  # no secret configured — open access (dev mode)
    return request.cookies.get(COOKIE_NAME) == DASHBOARD_SECRET


def require_auth(request: Request):
    """For page routes — redirect to login if not authenticated."""
    if not is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return None
