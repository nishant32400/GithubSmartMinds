"""Production WSGI entrypoint.

Run with gunicorn:
    gunicorn -c gunicorn.conf.py wsgi:app
"""
from app import app

# Gunicorn looks for the module-level ``app`` callable.
application = app
