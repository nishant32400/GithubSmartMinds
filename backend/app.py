"""Flask web + JSON API for the GitHub Talent Hunt agent.

Hardened for public internet exposure on AWS:
  * ProxyFix so client IPs/scheme come from the load balancer.
  * Per-IP rate limiting (Flask-Limiter).
  * Strict security headers + scoped CORS for the JSON API.
  * Server-side input clamping and sanitized error responses.
  * Debug mode only when explicitly enabled via APP_ENV.
"""
import argparse
import csv
import io
import json
import logging
import os
import re
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, render_template, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from agent import TalentHuntAgent
from config import config
from llm import get_llm_client
from scrapers.github_scraper import (
    GitHubAuthError,
    GitHubError,
    GitHubRateLimitError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("talenthunt")

TEMPLATES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "frontend")
)

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.config["SECRET_KEY"] = config.SECRET_KEY
# Honor X-Forwarded-* from the AWS load balancer (one proxy hop).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[config.RATELIMIT_DEFAULT],
    storage_uri=config.RATELIMIT_STORAGE_URI,
)
limiter.init_app(app)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; script-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
}


@app.after_request
def _apply_security_headers(response):
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    # Scoped CORS for the JSON API only.
    if request.path.startswith("/api/"):
        response.headers["Access-Control-Allow-Origin"] = config.CORS_ALLOWED_ORIGINS
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# --- helpers --------------------------------------------------------------
def _run_hunt(query, location, search_size, max_results):
    agent = TalentHuntAgent()
    return agent.hunt(
        requirements=query,
        location=location,
        search_size=search_size,
        top_n=max_results,
    )


def _error_response(exc):
    """Map an exception to a (safe_message, http_status) tuple."""
    if isinstance(exc, GitHubRateLimitError):
        return str(exc), 429
    if isinstance(exc, GitHubAuthError):
        return "Search service is misconfigured. Please contact the administrator.", 502
    if isinstance(exc, GitHubError):
        return str(exc), 502
    if isinstance(exc, ValueError):
        return str(exc), 400
    logger.exception("Unhandled error during hunt: %s", exc)
    return "An unexpected error occurred. Please try again later.", 500


def _trim_for_api(candidate):
    """Drop the bulky repo list from API payloads; keep ranking signal."""
    keep = (
        "username", "name", "bio", "location", "company", "blog", "followers",
        "public_repos", "avatar_url", "html_url", "skills", "score",
        "llm_score", "heuristic_score", "matched_skills", "missing_skills",
        "fit_summary", "evaluated_by", "achievements", "achievement_bonus",
        "total_stars", "total_forks",
    )
    return {k: candidate.get(k) for k in keep}


# --- search history (server-side, per browser session) --------------------
_HISTORY_KEY = "searches"
_HISTORY_MAX = 12


def _history():
    return session.get(_HISTORY_KEY, [])


def _record_search(query, location, max_results, search_size, count):
    """Prepend this search to the session history (dedup by query+location)."""
    q_key, loc_key = query.lower(), (location or "").lower()
    kept = [
        h for h in _history()
        if not (h.get("query", "").lower() == q_key
                and (h.get("location") or "").lower() == loc_key)
    ]
    kept.insert(0, {
        "query": query,
        "location": location,
        "max_results": max_results,
        "search_size": search_size,
        "count": count,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    })
    session[_HISTORY_KEY] = kept[:_HISTORY_MAX]
    return session[_HISTORY_KEY]


# --- CSV export -----------------------------------------------------------
# (source key, column header) in output order.
_CSV_FIELDS = (
    ("username", "Username"),
    ("name", "Name"),
    ("location", "Location"),
    ("score", "Score"),
    ("llm_fit", "AI Fit"),
    ("evaluated_by", "Evaluated By"),
    ("followers", "Followers"),
    ("public_repos", "Public Repos"),
    ("total_stars", "Total Stars"),
    ("matched_skills", "Matched Skills"),
    ("missing_skills", "Missing Skills"),
    ("achievements", "Achievements"),
    ("profile_url", "Profile URL"),
    ("fit_summary", "Fit Summary"),
)


def _csv_rows(candidates):
    """Flatten candidates into CSV-ready dicts (also embedded in the page)."""
    rows = []
    for c in candidates:
        rows.append({
            "username": c.get("username"),
            "name": c.get("name"),
            "location": c.get("location"),
            "score": c.get("score"),
            "llm_fit": c.get("llm_score"),
            "evaluated_by": c.get("evaluated_by"),
            "followers": c.get("followers"),
            "public_repos": c.get("public_repos"),
            "total_stars": c.get("total_stars"),
            "matched_skills": ", ".join(c.get("matched_skills") or c.get("skills") or []),
            "missing_skills": ", ".join(c.get("missing_skills") or []),
            "achievements": ", ".join(
                a.get("name", "") for a in (c.get("achievements") or []) if isinstance(a, dict)
            ),
            "profile_url": c.get("html_url"),
            "fit_summary": c.get("fit_summary"),
        })
    return rows


def _csv_safe(value):
    """Stringify a cell and neutralize spreadsheet formula injection."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@"):
        text = "'" + text
    return text


def _csv_filename(query):
    slug = re.sub(r"[^a-z0-9]+", "-", (query or "").lower()).strip("-") or "candidates"
    return f"gitradar-{slug[:40]}.csv"


# --- routes ---------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", history=_history())


@app.route("/search", methods=["POST"])
@limiter.limit(config.RATELIMIT_SEARCH)
def search():
    query = request.form.get("query", "").strip()
    location = request.form.get("location", "").strip()
    max_results = config.clamp_max_results(request.form.get("max_results"), default=10)
    search_size = config.clamp_search_size(request.form.get("search_size"), default=100)
    if not query:
        return render_template(
            "index.html", error="Please enter job requirements or keywords.",
            history=_history(),
        ), 400
    try:
        result = _run_hunt(query, location, search_size, max_results)
    except Exception as exc:  # mapped to a safe message below
        message, status = _error_response(exc)
        return render_template("index.html", error=message, history=_history()), status
    history = _record_search(query, location, max_results, search_size, result["count"])
    export_json = json.dumps({"query": query, "rows": _csv_rows(result["candidates"])})
    return render_template(
        "results.html",
        candidates=result["candidates"],
        query=query,
        location=location,
        plan=result["plan"],
        llm_enabled=result["llm_enabled"],
        llm_model=result["llm_model"],
        scanned=result["scanned"],
        history=history,
        export_json=export_json,
    )


@app.route("/export.csv", methods=["POST"])
@limiter.limit(config.RATELIMIT_SEARCH)
def export_csv():
    """Serialize the results embedded in the page into a downloadable CSV.

    The rows are POSTed back from the results page (no JS / no re-running the
    search), so the download always matches what the user is looking at.
    """
    try:
        data = json.loads(request.form.get("payload") or "{}")
    except ValueError:
        data = {}
    rows = data.get("rows")
    if not isinstance(rows, list):
        rows = []
    rows = rows[:config.MAX_RESULTS]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in _CSV_FIELDS])
    for r in rows:
        if isinstance(r, dict):
            writer.writerow([_csv_safe(r.get(key)) for key, _ in _CSV_FIELDS])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{_csv_filename(data.get("query"))}"',
        },
    )


@app.route("/api/search", methods=["POST", "OPTIONS"])
@limiter.limit(config.RATELIMIT_SEARCH)
def api_search():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    location = (data.get("location") or "").strip()
    max_results = config.clamp_max_results(data.get("max_results"), default=10)
    search_size = config.clamp_search_size(data.get("search_size"), default=100)
    if not query:
        return jsonify({"error": "query is required"}), 400
    try:
        result = _run_hunt(query, location, search_size, max_results)
    except Exception as exc:
        message, status = _error_response(exc)
        return jsonify({"error": message}), status
    return jsonify({
        "query": query,
        "location": location,
        "plan": result["plan"],
        "llm_enabled": result["llm_enabled"],
        "llm_model": result["llm_model"],
        "scanned": result["scanned"],
        "count": result["count"],
        "results": [_trim_for_api(c) for c in result["candidates"]],
    })


@app.route("/health", methods=["GET"])
@app.route("/healthz", methods=["GET"])
@limiter.exempt
def health():
    return jsonify({"status": "ok", "llm_enabled": get_llm_client().is_available()})


@app.errorhandler(429)
def _ratelimit_handler(exc):
    message = "Rate limit exceeded. Please slow down and try again shortly."
    if request.path.startswith("/api/"):
        return jsonify({"error": message}), 429
    return render_template("index.html", error=message, history=_history()), 429


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Talent Hunt web app (development server).")
    parser.add_argument("--host", default=config.HOST, help="Host to bind the server to.")
    parser.add_argument("--port", type=int, default=config.PORT, help="Port to bind the server to.")
    parser.add_argument("--debug", action="store_true", help="Force debug mode (development only).")
    args = parser.parse_args()

    debug = args.debug or config.DEBUG
    if debug:
        logger.warning("Starting in DEBUG mode - do not use this in production.")
    else:
        logger.warning("Development server. For production use: gunicorn -c gunicorn.conf.py wsgi:app")
    app.run(debug=debug, host=args.host, port=args.port)
