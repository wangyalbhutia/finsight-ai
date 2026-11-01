"""Vercel serverless entrypoint — exposes the FastAPI app.

The full application lives in the `app` package; Vercel routes every
request here via the rewrites in vercel.json. For container/local runs
use `uvicorn app.main:app` (see ../Dockerfile) instead.
"""
from app.main import app  # noqa: F401  (Vercel serves the ASGI `app`)
