from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import Base, engine
from app.models import models  # noqa
from app.api.v1.auth import router as auth_router
from app.api.v1.transactions import router as txn_router
from app.api.v1.resources import router as res_router
import time
from collections import defaultdict

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FinSight AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_hits = defaultdict(list)
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    now = time.time(); ip = request.client.host if request.client else "unknown"
    _hits[ip] = [t for t in _hits[ip] if now - t < 60]
    if len(_hits[ip]) >= settings.rate_limit_per_minute:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    _hits[ip].append(now)
    return await call_next(request)

@app.get("/health")
def health():
    return {"status": "ok", "service": "FinSight AI"}

app.include_router(auth_router, prefix="/api/v1")
app.include_router(txn_router, prefix="/api/v1")
app.include_router(res_router, prefix="/api/v1")
