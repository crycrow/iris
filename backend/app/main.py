from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.database import SessionLocal, get_db
from app.core.config import settings
from app.core import scheduler
from app.common.routers import auth, users, projects, settings as settings_router
from app.common.services.access_log import configure_access_log, audit
from app.core.integration import router as integration_router, configure_providers


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_access_log()
    configure_providers()
    if settings.seed_demo:
        from app.seed.demo import seed_all

        with SessionLocal.begin() as db:
            seed_all(db)
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="ИС управления рисками IT-проектов", version="3.0.0", lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in (
    auth.router,
    users.router,
    projects.router,
    settings_router.router,
    integration_router,
):
    app.include_router(router)


@app.get("/api/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, error: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={"detail": "Операция нарушает целостность данных или создаёт дубликат"},
    )


from app.modules.time_tracking.routers import router as time_router
from app.modules.risk_management.routers import router as risk_router

app.include_router(time_router)
app.include_router(risk_router)


@app.middleware("http")
async def audit_personal_access(request: Request, call_next):
    response = await call_next(request)
    user_id = getattr(request.state, "user_id", None)
    if user_id and request.url.path.startswith("/api/") and response.status_code < 400:
        audit(user_id, request.method, request.url.path)
    return response
