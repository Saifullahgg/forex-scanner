"""
Vercel serverless entry point.

Vercel auto-detects Python functions in the api/ directory and serves the
FastAPI application (ASGI) defined in webapp.app as the app object.

The catch-all rewrite in vercel.json routes every request here, so the
FastAPI routes (/api/health, /api/scan, /api/pair/{pair}/chart, /static, /)
all work unchanged on Vercel.
"""

from webapp.app import app  # noqa: F401  (Vercel imports `app` from this module)
