from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from langchain_google_genai._common import GoogleGenerativeAIError
from pymongo.errors import PyMongoError

from app.auth import router as auth_router
from app.chat import router as chat_router
from app.config import settings
from app.documents import router as documents_router
from app.subjects import router as subjects_router
from app.templates import templates

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Exam Partner")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router)
app.include_router(subjects_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/subjects", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(HTTPException)
async def redirect_unauthenticated_to_login(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)
    return await http_exception_handler(request, exc)


def _service_error(request: Request, emoji: str, heading: str, detail: str):
    """Render an outage as something a student can act on.

    HTMX callers get a small fragment: a full page swapped into a polling
    target or the chat thread would wreck the layout.
    """
    context = {"emoji": emoji, "heading": heading, "detail": detail}
    template = (
        "partials/_service_alert.html" if request.headers.get("HX-Request") else "service_error.html"
    )
    return templates.TemplateResponse(request, template, context, status_code=503)


@app.exception_handler(PyMongoError)
async def database_unavailable(request: Request, exc: PyMongoError):
    return _service_error(
        request,
        "🔌",
        "Can't reach the database",
        "Your study library is temporarily unreachable. If you're using a free MongoDB Atlas "
        "cluster, it may have paused — resume it from the Atlas dashboard and try again.",
    )


@app.exception_handler(GoogleGenerativeAIError)
async def ai_unavailable(request: Request, exc: GoogleGenerativeAIError):
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        heading = "Daily AI limit reached"
        detail = (
            "You've used today's free AI request allowance. The quota resets daily — "
            "try again in a little while."
        )
    else:
        heading = "The AI service is unavailable"
        detail = "Answering is temporarily unavailable. Please try again in a moment."
    return _service_error(request, "✨", heading, detail)
