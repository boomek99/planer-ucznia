"""Small Render API for one-off Librus schedule reads.

Librus credentials are accepted for one request only and are never written to
disk, a database, logs, or an application session.
"""
import os
import threading
import time
from datetime import date, datetime

import requests
from flask import Flask, jsonify, make_response, request
from librus_apix.client import new_client
from librus_apix.schedule import get_schedule, schedule_detail

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://boomek99.github.io")
_attempts = {}
_attempts_lock = threading.Lock()


def response(payload, status=200):
    res = make_response(jsonify(payload), status)
    origin = request.headers.get("Origin")
    if origin == ALLOWED_ORIGIN:
        res.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        res.headers["Access-Control-Max-Age"] = "600"
        res.headers["Vary"] = "Origin"
    res.headers["Cache-Control"] = "no-store"
    res.headers["X-Content-Type-Options"] = "nosniff"
    return res


def validate_user():
    if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
        return False
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    try:
        check = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_PUBLISHABLE_KEY, "Authorization": header},
            timeout=10,
        )
        if check.status_code == 200:
            return check.json().get("id")
        return None
    except (requests.RequestException, ValueError):
        return None


def within_rate_limit(user_id):
    now = time.monotonic()
    with _attempts_lock:
        recent = [at for at in _attempts.get(user_id, []) if now - at < 600]
        if len(recent) >= 5:
            _attempts[user_id] = recent
            return False
        recent.append(now)
        _attempts[user_id] = recent
        return True


def normalize_date(year, month, value):
    try:
        return datetime(year, month, int(str(value).strip())).date().isoformat()
    except (ValueError, TypeError):
        text = str(value)
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None


def fetch_events(username, password, start, end):
    client = new_client()
    client.get_token(username, password)
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    items = []
    while (y, m) <= (ey, em):
        schedule = get_schedule(client, str(m), str(y))
        for day, day_events in schedule.items():
            for event in day_events:
                title = str(getattr(event, "title", None) or event)[:300]
                subject = getattr(event, "subject", None)
                href = getattr(event, "href", None)
                if href and subject:
                    title = f"{title} — {str(subject)[:150]}"
                event_date = normalize_date(y, m, getattr(event, "date", None) or day)
                if not event_date:
                    continue
                description = ""
                if href:
                    try:
                        prefix, handle = href.split("/", 1)
                        detail = schedule_detail(client, prefix, handle)
                        if isinstance(detail, dict):
                            description = "\n".join(f"{k}: {v}" for k, v in detail.items())
                        elif hasattr(detail, "__dict__"):
                            description = "\n".join(f"{k}: {v}" for k, v in vars(detail).items())
                        else:
                            description = str(detail)
                    except Exception:
                        description = ""
                items.append({"title": title, "date": event_date, "description": description[:2000]})
        m += 1
        if m > 12:
            y, m = y + 1, 1
    del client
    return items


@app.get("/health")
def health():
    return response({"ok": True, "librus_configured": bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY)})


@app.route("/api/librus/schedule", methods=["POST", "OPTIONS"])
def librus_schedule():
    if request.method == "OPTIONS":
        return response({"ok": True})
    if request.headers.get("Origin") != ALLOWED_ORIGIN:
        return response({"error": "Nieprawidłowe źródło żądania."}, 403)
    user_id = validate_user()
    if not user_id:
        return response({"error": "Sesja wygasła. Zaloguj się ponownie."}, 401)
    if not within_rate_limit(user_id):
        return response({"error": "Za dużo prób. Odczekaj 10 minut i spróbuj ponownie."}, 429)
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    start = str(body.get("start", ""))
    end = str(body.get("end", ""))
    if not username or len(username) > 150 or not password or len(password) > 512:
        return response({"error": "Wpisz login i hasło Librusa."}, 400)
    try:
        start_date = date.fromisoformat(start + "-01")
        end_date = date.fromisoformat(end + "-01")
        month_gap = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
        if month_gap not in (0, 1):
            raise ValueError
    except ValueError:
        return response({"error": "Wybierz jeden lub dwa kolejne miesiące."}, 400)
    try:
        events = fetch_events(username, password, start, end)
    except Exception as exc:
        # Do not log exception messages: third-party errors may contain request data.
        app.logger.warning("Librus request failed (%s)", type(exc).__name__)
        return response({"error": "Nie udało się pobrać terminarza. Sprawdź dane i spróbuj ponownie."}, 422)
    finally:
        password = ""
    return response({"events": events})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
