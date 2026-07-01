"""Gunicorn configuration tuned for an I/O-bound (network + LLM) workload."""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# The work is I/O bound (GitHub + LLM calls), so use threaded workers.
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# LLM evaluation can take time; allow generous request timeouts.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

# Log to stdout/stderr so AWS (CloudWatch / ECS) can collect them.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
