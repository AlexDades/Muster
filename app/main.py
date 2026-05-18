import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.api import documents, drafts, audit, settings_api, inbox, chat
from app.api import onboarding as onboarding_api
from app.api.auth_api import router as auth_router
from app.ms365.oauth import router as ms365_router
from app.auth.jwt_auth import require_auth
from app.config import settings

logger = logging.getLogger("muster.poller")

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


async def _poll_loop() -> None:
    import anthropic
    from app.dependencies import get_inbox, get_policy_store, get_draft_store, get_runtime_settings
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    while True:
        try:
            inbox_obj = get_inbox()
            store = get_policy_store()
            rt = get_runtime_settings()
            draft_store = get_draft_store() if rt.human_review_mode else None
            from app.email_ingestion.poller import process_inbox
            results = process_inbox(
                inbox=inbox_obj,
                store=store,
                client=client,
                human_review_mode=rt.human_review_mode,
                draft_store=draft_store,
            )
            if results:
                logger.info("Poll: processed %d email(s)", len(results))
        except Exception:
            logger.exception("Poll cycle failed")

        try:
            from app.onboarding.store import OnboardingStore
            from app.email_utils import send_email
            from datetime import date
            today = date.today().isoformat()
            ob_store = OnboardingStore(db_path=settings.db_path)
            due = ob_store.get_due_deliveries(today)
            for delivery in due:
                delivery_id = delivery["delivery_id"]
                try:
                    step_body = delivery["body"].replace("{employee_name}", delivery["employee_name"])
                    file_link = f"{settings.public_base_url}/files/{delivery['doc_name']}"
                    full_body = f"{step_body}\n\n{file_link}"
                    send_email(
                        to=delivery["employee_email"],
                        subject=delivery["subject"],
                        body=full_body,
                    )
                    ob_store.mark_delivery_sent(delivery_id)
                    logger.info(
                        "Onboarding: sent delivery %d to %s",
                        delivery_id,
                        delivery["employee_email"],
                    )
                except Exception:
                    ob_store.mark_delivery_failed(delivery_id)
                    logger.exception(
                        "Onboarding: failed delivery %d to %s",
                        delivery_id,
                        delivery["employee_email"],
                    )
        except Exception:
            logger.exception("Onboarding delivery cycle failed")

        await asyncio.sleep(settings.poll_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ngrok_auth_token:
        try:
            from pyngrok import ngrok, conf
            conf.get_default().auth_token = settings.ngrok_auth_token
            tunnel = ngrok.connect(8000, "http")
            settings.public_base_url = tunnel.public_url
            logger.info("ngrok tunnel active: %s", tunnel.public_url)
        except Exception:
            logger.exception("ngrok tunnel failed to start — using PUBLIC_BASE_URL from .env")

    task = asyncio.create_task(_poll_loop())
    logger.info("Background inbox poller started (every %ds)", settings.poll_interval_seconds)
    yield
    task.cancel()
    if settings.ngrok_auth_token:
        from pyngrok import ngrok
        ngrok.kill()


app = FastAPI(
    title="Muster HR Policy Assistant",
    description="Automatically answers employee HR policy questions via email.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


_auth_dep = [Depends(require_auth)]

app.include_router(auth_router)
app.include_router(ms365_router, dependencies=_auth_dep)
app.include_router(documents.router, dependencies=_auth_dep)
app.include_router(drafts.router, dependencies=_auth_dep)
app.include_router(audit.router, dependencies=_auth_dep)
app.include_router(settings_api.router, dependencies=_auth_dep)
app.include_router(inbox.router, dependencies=_auth_dep)
app.include_router(chat.router, dependencies=_auth_dep)
app.include_router(onboarding_api.router, dependencies=_auth_dep)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DOCS_DIR = Path(settings.uploaded_docs_dir)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(DOCS_DIR)), name="files")


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "public_base_url": settings.public_base_url}


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(str(STATIC_DIR / "index.html"))
