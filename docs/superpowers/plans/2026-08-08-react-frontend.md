# React Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Jinja2/HTMX frontend with a React single-page application in the approved monochrome design, backed by a new JSON API over the existing FastAPI domain logic, with cookie-session auth that survives refresh.

**Architecture:** The existing FastAPI app gains a `/api/*` JSON layer that reuses its already-tested domain functions (`create_subject`, `process_document`, `answer_question`, …) — no RAG behavior changes. A React 18 + TypeScript SPA built with Vite consumes that API. In development Vite proxies `/api` to FastAPI so the browser sees one origin (no CORS, cookies behave as in production). In production FastAPI serves the built SPA and returns `index.html` for non-`/api` paths.

**Tech Stack:** Backend — FastAPI, Pydantic v2, pymongo, pytest, mongomock. Frontend — React 18, TypeScript, Vite 5, React Router 6, TanStack Query 5, plain CSS custom properties, Vitest, React Testing Library, MSW. Fonts — `@fontsource-variable/instrument-sans`, `@fontsource/ibm-plex-mono`.

## Global Constraints

- **Design contract:** the approved mockup is https://claude.ai/code/artifact/4bdb815a-4f06-4abb-b8ff-f71169df65b3 — match it. White paper canvas; near-black `#0C0C0D` is the only accent (buttons, avatar, logo mark, active nav are solid black). No brand hue.
- Neutrals carry a warm bias (`#FAF9F7`, `#E7E5E1`) — never generic slate greys.
- Status color is the **only** color, desaturated, rendered as a 5px dot plus a small mono label — never a filled badge.
- Instrument Sans for prose; IBM Plex Mono for data (filenames, counts, timestamps, section labels, citation numbers).
- Hairline 1px borders, radii 6–8px, no decorative shadows except one soft shadow on popover menus.
- Both light and dark themes required; every color read from a token in `tokens.css`, never hardcoded in a component.
- **No endpoint under `/api/` may ever return an HTML redirect.** Unauthenticated `/api/*` returns JSON `401`.
- Every API endpoint is scoped to the session user: one user must never read another's subjects, documents, or messages.
- No changes to RAG, extraction, chunking, embedding, or retrieval behavior.
- All backend collection-accessing functions take `db` explicitly (never a module global) so tests inject `mongomock`.
- Backend tests run with `.venv/Scripts/python -m pytest` (plain `pytest` does not put the project root on `sys.path` on this machine).

## File Structure

**Backend — new**

| File | Responsibility |
|---|---|
| `app/serializers.py` | Convert Mongo documents to JSON-safe API dicts. Pure functions, no DB access. |
| `app/api/__init__.py` | Marks `app.api` a package. |
| `app/api/deps.py` | `api_current_user` dependency — JSON `401`, never a redirect. |
| `app/api/auth.py` | `/api/auth/signup`, `/login`, `/logout`, `/me`. |
| `app/api/subjects.py` | `/api/subjects` CRUD plus per-subject summary counts. |
| `app/api/documents.py` | `/api/subjects/{id}/documents` list, upload, delete. |
| `app/api/chat.py` | `/api/subjects/{id}/messages` list, ask, ask-general. |

**Backend — modified**

| File | Change |
|---|---|
| `app/config.py` | Add session cookie lifetime and `https_only` settings. |
| `app/main.py` | 401 handler skips `/api/`; mount API routers; (Task 17) serve the SPA build. |
| `app/chat.py` | Persist `found` on saved messages. |
| `app/documents.py` | Add `delete_document` (removes the document **and** its vector chunks). |
| `app/subjects.py` | Add `list_subject_summaries` (counts + last-asked per subject). |

**Frontend — `frontend/`**

| File | Responsibility |
|---|---|
| `vite.config.ts` | Build config + `/api` dev proxy to `http://127.0.0.1:8000`. |
| `src/styles/tokens.css` | The palette, type stack, radii — light and dark. Single source of design truth. |
| `src/styles/base.css` | Reset, body/heading typography, the `.mono` utility. |
| `src/styles/components.css` | `.btn`, `.field`, `.status`, `.card` primitives. |
| `src/styles/layout.css` | `.app`, `.side`, `.top`, `.sess`, `.body-pad` app shell. |
| `src/styles/pages.css` | Auth, subjects table, split view, sources rail, chat. |
| `src/lib/types.ts` | Shared TypeScript types mirroring the API contract. |
| `src/lib/api.ts` | The only place that calls `fetch`. Sends credentials, throws `ApiError`. |
| `src/lib/citations.ts` | `numberCitations` — dedupe + number a message's citations. |
| `src/auth/AuthContext.tsx` | Session bootstrap, `useAuth`, login/signup/logout actions. |
| `src/auth/ProtectedRoute.tsx` | Redirects unauthenticated users to `/login`. |
| `src/components/Button.tsx`, `Field.tsx`, `StatusDot.tsx`, `Card.tsx` | Presentational primitives, no data fetching. |
| `src/components/AppShell.tsx` | Sidebar + topbar + session menu; wraps authenticated pages. |
| `src/pages/LoginPage.tsx`, `SignupPage.tsx`, `SubjectsPage.tsx`, `SubjectDetailPage.tsx` | Route-level screens. |
| `src/features/subjects/SubjectsTable.tsx`, `useSubjects.ts` | Subjects table + its queries/mutations. |
| `src/features/documents/SourcesPanel.tsx`, `useDocuments.ts` | Dropzone, source list, status polling, delete. |
| `src/features/chat/ChatPanel.tsx`, `ChatMessage.tsx`, `useChat.ts` | Thread, composer, message variants. |
| `src/test/setup.ts`, `src/test/server.ts` | Vitest setup and MSW handlers. |

---

### Task 1: Session cookie settings and API-safe 401 handling

**Files:**
- Modify: `app/config.py`
- Modify: `app/main.py:13` (middleware), `app/main.py:32-36` (exception handler)
- Create: `app/api/__init__.py`
- Create: `app/api/deps.py`
- Test: `tests/test_api_deps.py`

**Interfaces:**
- Consumes: `app.auth.get_current_user`, `app.db.get_db`.
- Produces: `app.api.deps.api_current_user(request, db) -> dict` (FastAPI dependency returning the user document, raising JSON `HTTPException(401, "Not authenticated")`); `settings.session_max_age: int`; `settings.session_https_only: bool`.

- [ ] **Step 1: Write the failing test**

This exercises the real app through a temporary `/api/auth/me` route added in Step 6; Task 2 replaces that stub with the real auth router and these tests keep passing unchanged.

```python
# tests/test_api_deps.py
def test_api_401_is_json_not_redirect(client):
    response = client.get("/api/auth/me", follow_redirects=False)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_api_me_returns_the_session_user(authed_client):
    client, user = authed_client
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"user": {"id": user["_id"], "email": user["email"]}}


def test_non_api_401_still_redirects_to_login(client):
    response = client.get("/subjects", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_deps.py -v`
Expected: FAIL — `/api/auth/me` returns 404 because neither the route nor `app.api` exists yet.

- [ ] **Step 3: Create the API package and dependency**

Create `app/api/__init__.py` as an empty file. Then create `app/api/deps.py`:

```python
from fastapi import Depends, HTTPException, Request
from pymongo.database import Database

from app.db import get_db, users_collection


def api_current_user(request: Request, db: Database = Depends(get_db)) -> dict:
    """Session-authenticated user for JSON endpoints.

    Raises a plain 401 so the SPA can react; app.main's redirecting 401
    handler deliberately skips paths under /api/.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = users_collection(db).find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
```

- [ ] **Step 4: Add session settings to `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mongodb_uri: str
    mongodb_db_name: str = "exam_partner"
    gemini_api_key: str
    session_secret: str
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days
    session_https_only: bool = False  # set true when served over HTTPS


settings = Settings()
```

- [ ] **Step 5: Update `app/main.py` — explicit cookie settings and API-safe 401**

Replace the `add_middleware` call and the exception handler:

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="kb_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.session_https_only,
)
```

```python
@app.exception_handler(HTTPException)
async def redirect_unauthenticated_to_login(request: Request, exc: HTTPException):
    # JSON clients under /api/ must receive a real 401, never an HTML redirect.
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(url="/login", status_code=303)
    return await http_exception_handler(request, exc)
```

- [ ] **Step 6: Add a temporary `/api/auth/me` so the dependency is reachable**

Add to `app/main.py` — Task 2 deletes this and mounts the real auth router in its place.

```python
from fastapi import Depends  # add with the other imports

from app.api.deps import api_current_user  # add with the other imports


@app.get("/api/auth/me")
def api_me_stub(user: dict = Depends(api_current_user)):
    return {"user": {"id": user["_id"], "email": user["email"]}}
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (57 tests: the previous 54 plus 3 new).

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/main.py app/api tests/test_api_deps.py
git commit -m "feat: add API auth dependency with JSON 401 and explicit session cookie settings"
```

---

### Task 2: Serializers and the auth API

**Files:**
- Create: `app/serializers.py`
- Create: `app/api/auth.py`
- Modify: `app/main.py` (include the auth API router, remove the Task 1 stub)
- Test: `tests/test_serializers.py`, `tests/test_api_auth.py`

**Interfaces:**
- Consumes: `app.auth.create_user`, `app.auth.authenticate_user`, `app.api.deps.api_current_user`.
- Produces: `serialize_user(user) -> dict`, `serialize_subject(subject) -> dict`, `serialize_document(document) -> dict`, `serialize_message(message) -> dict`; router mounted at `/api/auth`.

- [ ] **Step 1: Write the failing serializer test**

```python
# tests/test_serializers.py
from datetime import datetime, timezone

from app.serializers import serialize_document, serialize_message, serialize_subject, serialize_user

WHEN = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def test_serialize_user_exposes_id_and_email_only():
    user = {"_id": "u1", "email": "a@b.com", "password_hash": "secret-hash", "created_at": WHEN}
    assert serialize_user(user) == {"id": "u1", "email": "a@b.com"}


def test_serialize_subject_renames_id_and_isoformats_dates():
    subject = {"_id": "s1", "user_id": "u1", "name": "Physics", "created_at": WHEN}
    result = serialize_subject(subject)
    assert result["id"] == "s1"
    assert result["name"] == "Physics"
    assert result["created_at"] == "2026-08-08T12:00:00+00:00"
    assert "user_id" not in result


def test_serialize_document_includes_status_and_error():
    document = {
        "_id": "d1", "user_id": "u1", "subject_id": "s1", "filename": "a.pdf",
        "status": "failed", "error": "No readable text found in file", "created_at": WHEN,
    }
    result = serialize_document(document)
    assert result == {
        "id": "d1", "filename": "a.pdf", "status": "failed",
        "error": "No readable text found in file", "created_at": "2026-08-08T12:00:00+00:00",
    }


def test_serialize_message_passes_through_stored_found_flag():
    message = {
        "_id": "m1", "user_id": "u1", "subject_id": "s1", "question": "q", "answer": "a",
        "citations": [{"filename": "a.pdf", "source_label": "page 1"}],
        "response_mode": "rag", "found": True, "created_at": WHEN,
    }
    assert serialize_message(message)["found"] is True


def test_serialize_message_infers_found_for_legacy_messages_without_the_flag():
    grounded = {
        "_id": "m1", "user_id": "u1", "subject_id": "s1", "question": "q", "answer": "a",
        "citations": [{"filename": "a.pdf", "source_label": "page 1"}],
        "response_mode": "rag", "created_at": WHEN,
    }
    missing = {
        "_id": "m2", "user_id": "u1", "subject_id": "s1", "question": "q",
        "answer": "Not found in your uploaded material.", "citations": [],
        "response_mode": "rag", "created_at": WHEN,
    }
    general = {
        "_id": "m3", "user_id": "u1", "subject_id": "s1", "question": "q", "answer": "a",
        "citations": [], "response_mode": "general", "created_at": WHEN,
    }
    assert serialize_message(grounded)["found"] is True
    assert serialize_message(missing)["found"] is False
    assert serialize_message(general)["found"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_serializers.py -v`
Expected: FAIL — `No module named 'app.serializers'`.

- [ ] **Step 3: Write `app/serializers.py`**

```python
from datetime import datetime


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_user(user: dict) -> dict:
    return {"id": user["_id"], "email": user["email"]}


def serialize_subject(subject: dict) -> dict:
    return {
        "id": subject["_id"],
        "name": subject["name"],
        "created_at": _iso(subject.get("created_at")),
    }


def serialize_document(document: dict) -> dict:
    return {
        "id": document["_id"],
        "filename": document["filename"],
        "status": document["status"],
        "error": document.get("error"),
        "created_at": _iso(document.get("created_at")),
    }


def serialize_message(message: dict) -> dict:
    found = message.get("found")
    if found is None:
        # Messages stored before `found` was persisted: a RAG answer with no
        # citations is exactly the "not found in your material" case.
        found = not (message["response_mode"] == "rag" and not message["citations"])
    return {
        "id": message["_id"],
        "question": message["question"],
        "answer": message["answer"],
        "citations": message["citations"],
        "response_mode": message["response_mode"],
        "found": found,
        "created_at": _iso(message.get("created_at")),
    }
```

- [ ] **Step 4: Run the serializer test**

Run: `.venv/Scripts/python -m pytest tests/test_serializers.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing auth API test**

```python
# tests/test_api_auth.py
def test_signup_creates_session_and_returns_user(client):
    response = client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "s@e.com"
    assert "id" in response.json()["user"]

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "s@e.com"


def test_signup_rejects_duplicate_email(client):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    response = client.post("/api/auth/signup", json={"email": "s@e.com", "password": "different1"})
    assert response.status_code == 400
    assert response.json()["detail"] == "That email is already registered"


def test_signup_rejects_short_password(client):
    response = client.post("/api/auth/signup", json={"email": "s@e.com", "password": "short"})
    assert response.status_code == 422


def test_login_succeeds_and_opens_session(client):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json={"email": "s@e.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "s@e.com"
    assert client.get("/api/auth/me").status_code == 200


def test_login_with_wrong_password_returns_401(client):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json={"email": "s@e.com", "password": "wrong-pass"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_logout_clears_the_session(client):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_me_without_session_returns_401(client):
    assert client.get("/api/auth/me").status_code == 401
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_auth.py -v`
Expected: FAIL — signup returns 404 (route does not exist).

- [ ] **Step 7: Write `app/api/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from pymongo.database import Database

from app.api.deps import api_current_user
from app.auth import authenticate_user, create_user
from app.db import get_db
from app.serializers import serialize_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginCredentials(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup", status_code=201)
def signup(payload: Credentials, request: Request, db: Database = Depends(get_db)):
    try:
        user = create_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session["user_id"] = user["_id"]
    return {"user": serialize_user(user)}


@router.post("/login")
def login(payload: LoginCredentials, request: Request, db: Database = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session["user_id"] = user["_id"]
    return {"user": serialize_user(user)}


@router.post("/logout", status_code=204)
def logout(request: Request):
    request.session.clear()
    return Response(status_code=204)


@router.get("/me")
def me(user: dict = Depends(api_current_user)):
    return {"user": serialize_user(user)}
```

- [ ] **Step 8: Wire it into `app/main.py`**

Remove the `api_me_stub` route added in Task 1 (and its now-unused `Depends` / `api_current_user` imports if nothing else uses them), then add:

```python
from app.api.auth import router as api_auth_router
...
app.include_router(api_auth_router)
```

`EmailStr` requires the `email-validator` package. Add `email-validator` to `requirements.txt` and install it:

```bash
.venv/Scripts/pip install email-validator
```

- [ ] **Step 9: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_api_auth.py tests/test_api_deps.py -v`
Expected: PASS (9 tests).

- [ ] **Step 10: Commit**

```bash
git add app/serializers.py app/api/auth.py app/main.py requirements.txt tests/test_serializers.py tests/test_api_auth.py
git commit -m "feat: add JSON auth API with signup, login, logout, and session bootstrap"
```

---

### Task 3: Subjects API with summary counts

**Files:**
- Modify: `app/subjects.py` (add `list_subject_summaries`)
- Create: `app/api/subjects.py`
- Modify: `app/main.py` (include router)
- Test: `tests/test_subject_summaries.py`, `tests/test_api_subjects.py`

**Interfaces:**
- Consumes: `app.subjects.create_subject/list_subjects/get_subject/rename_subject/delete_subject`, `app.documents.list_documents`, `app.db.chats_collection`, `app.api.deps.api_current_user`, `app.serializers.serialize_subject`.
- Produces: `list_subject_summaries(db, user_id) -> list[dict]` where each dict is `serialize_subject(...)` plus `document_count: int`, `processing_count: int`, `failed_count: int`, `last_asked_at: str | None`; router at `/api/subjects`.

- [ ] **Step 1: Write the failing summary test**

```python
# tests/test_subject_summaries.py
from datetime import datetime, timezone

from app.chat import save_chat_message
from app.documents import create_document, mark_document
from app.subjects import create_subject, list_subject_summaries


def _result():
    return {"answer": "a", "citations": [], "response_mode": "general", "found": True}


def test_summary_counts_documents_by_status(db):
    subject = create_subject(db, "u1", "Physics")
    ready = create_document(db, "u1", subject["_id"], "ready.pdf")
    mark_document(db, ready["_id"], "ready")
    failed = create_document(db, "u1", subject["_id"], "bad.pdf")
    mark_document(db, failed["_id"], "failed", "No readable text found in file")
    create_document(db, "u1", subject["_id"], "busy.pdf")  # stays "processing"

    summary = list_subject_summaries(db, "u1")[0]

    assert summary["document_count"] == 3
    assert summary["processing_count"] == 1
    assert summary["failed_count"] == 1


def test_summary_reports_last_asked_at(db):
    subject = create_subject(db, "u1", "Physics")
    assert list_subject_summaries(db, "u1")[0]["last_asked_at"] is None

    save_chat_message(db, "u1", subject["_id"], "q", _result())
    assert list_subject_summaries(db, "u1")[0]["last_asked_at"] is not None


def test_summary_is_scoped_to_the_user(db):
    mine = create_subject(db, "u1", "Physics")
    theirs = create_subject(db, "u2", "Physics")
    create_document(db, "u2", theirs["_id"], "not-mine.pdf")

    summaries = list_subject_summaries(db, "u1")

    assert len(summaries) == 1
    assert summaries[0]["id"] == mine["_id"]
    assert summaries[0]["document_count"] == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_subject_summaries.py -v`
Expected: FAIL — `cannot import name 'list_subject_summaries'`.

- [ ] **Step 3: Add `list_subject_summaries` to `app/subjects.py`**

Add these imports at the top of the file (`chats_collection` alongside the existing `get_db, subjects_collection` import), then append the function:

```python
from app.db import chats_collection, get_db, subjects_collection
from app.serializers import serialize_subject
```

```python
def list_subject_summaries(db: Database, user_id: str) -> list[dict]:
    """Subjects plus the counts the subjects table displays.

    Counted in Python rather than an aggregation pipeline so the same code
    runs against mongomock in tests.
    """
    summaries = []
    for subject in list_subjects(db, user_id):
        documents = list_documents(db, user_id, subject["_id"])
        latest = list(
            chats_collection(db)
            .find({"user_id": user_id, "subject_id": subject["_id"]})
            .sort("created_at", -1)
            .limit(1)
        )
        last_asked = latest[0]["created_at"] if latest else None
        summaries.append(
            {
                **serialize_subject(subject),
                "document_count": len(documents),
                "processing_count": sum(1 for d in documents if d["status"] == "processing"),
                "failed_count": sum(1 for d in documents if d["status"] == "failed"),
                "last_asked_at": last_asked.isoformat() if last_asked else None,
            }
        )
    return summaries
```

- [ ] **Step 4: Run the summary test**

Run: `.venv/Scripts/python -m pytest tests/test_subject_summaries.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing subjects API test**

```python
# tests/test_api_subjects.py
import pytest


@pytest.fixture
def api_client(client):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    return client


def test_list_subjects_starts_empty(api_client):
    response = api_client.get("/api/subjects")
    assert response.status_code == 200
    assert response.json() == {"subjects": []}


def test_create_then_list_subject_includes_summary_fields(api_client):
    created = api_client.post("/api/subjects", json={"name": "Physics"})
    assert created.status_code == 201
    assert created.json()["subject"]["name"] == "Physics"

    listed = api_client.get("/api/subjects").json()["subjects"]
    assert len(listed) == 1
    assert listed[0]["document_count"] == 0
    assert listed[0]["processing_count"] == 0
    assert listed[0]["failed_count"] == 0
    assert listed[0]["last_asked_at"] is None


def test_create_subject_rejects_blank_name(api_client):
    assert api_client.post("/api/subjects", json={"name": "   "}).status_code == 422


def test_get_subject_returns_it(api_client):
    subject_id = api_client.post("/api/subjects", json={"name": "Physics"}).json()["subject"]["id"]
    response = api_client.get(f"/api/subjects/{subject_id}")
    assert response.status_code == 200
    assert response.json()["subject"]["name"] == "Physics"


def test_get_missing_subject_returns_404(api_client):
    assert api_client.get("/api/subjects/does-not-exist").status_code == 404


def test_rename_subject(api_client):
    subject_id = api_client.post("/api/subjects", json={"name": "Thermo"}).json()["subject"]["id"]
    response = api_client.patch(f"/api/subjects/{subject_id}", json={"name": "Thermodynamics"})
    assert response.status_code == 200
    assert response.json()["subject"]["name"] == "Thermodynamics"


def test_delete_subject(api_client):
    subject_id = api_client.post("/api/subjects", json={"name": "Physics"}).json()["subject"]["id"]
    assert api_client.delete(f"/api/subjects/{subject_id}").status_code == 204
    assert api_client.get("/api/subjects").json()["subjects"] == []


def test_subjects_require_authentication(client):
    assert client.get("/api/subjects").status_code == 401


def test_one_user_cannot_read_another_users_subject(api_client, db):
    from app.subjects import create_subject

    other = create_subject(db, "someone-else", "Not Yours")
    assert api_client.get(f"/api/subjects/{other['_id']}").status_code == 404
    assert api_client.get("/api/subjects").json()["subjects"] == []
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_subjects.py -v`
Expected: FAIL — 404s, the routes do not exist.

- [ ] **Step 7: Write `app/api/subjects.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from app.api.deps import api_current_user
from app.db import get_db
from app.serializers import serialize_subject
from app.subjects import (
    create_subject,
    delete_subject,
    get_subject,
    list_subject_summaries,
    rename_subject,
)

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


class SubjectName(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name cannot be blank")
        return cleaned


def _require_subject(db: Database, user_id: str, subject_id: str) -> dict:
    subject = get_subject(db, user_id, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("")
def list_route(db: Database = Depends(get_db), user: dict = Depends(api_current_user)):
    return {"subjects": list_subject_summaries(db, user["_id"])}


@router.post("", status_code=201)
def create_route(
    payload: SubjectName, db: Database = Depends(get_db), user: dict = Depends(api_current_user)
):
    subject = create_subject(db, user["_id"], payload.name)
    return {"subject": serialize_subject(subject)}


@router.get("/{subject_id}")
def get_route(
    subject_id: str, db: Database = Depends(get_db), user: dict = Depends(api_current_user)
):
    return {"subject": serialize_subject(_require_subject(db, user["_id"], subject_id))}


@router.patch("/{subject_id}")
def rename_route(
    subject_id: str,
    payload: SubjectName,
    db: Database = Depends(get_db),
    user: dict = Depends(api_current_user),
):
    _require_subject(db, user["_id"], subject_id)
    rename_subject(db, user["_id"], subject_id, payload.name)
    return {"subject": serialize_subject(get_subject(db, user["_id"], subject_id))}


@router.delete("/{subject_id}", status_code=204)
def delete_route(
    subject_id: str, db: Database = Depends(get_db), user: dict = Depends(api_current_user)
):
    _require_subject(db, user["_id"], subject_id)
    delete_subject(db, user["_id"], subject_id)
    return Response(status_code=204)
```

- [ ] **Step 8: Include the router in `app/main.py`**

```python
from app.api.subjects import router as api_subjects_router
...
app.include_router(api_subjects_router)
```

- [ ] **Step 9: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_api_subjects.py tests/test_subject_summaries.py -v`
Expected: PASS (12 tests).

- [ ] **Step 10: Commit**

```bash
git add app/subjects.py app/api/subjects.py app/main.py tests/test_api_subjects.py tests/test_subject_summaries.py
git commit -m "feat: add subjects JSON API with per-subject document and activity counts"
```

---

### Task 4: Documents API with delete

**Files:**
- Modify: `app/documents.py` (add `delete_document`)
- Create: `app/api/documents.py`
- Modify: `app/main.py` (include router)
- Test: `tests/test_document_delete.py`, `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `app.documents.create_document/list_documents/save_upload/process_document`, `app.db.chunks_collection`, `app.subjects.get_subject`, `app.api.deps.api_current_user`, `app.serializers.serialize_document`.
- Produces: `delete_document(db, user_id, subject_id, document_id) -> bool`; router at `/api/subjects/{subject_id}/documents`.

- [ ] **Step 1: Write the failing delete test**

```python
# tests/test_document_delete.py
from app.db import chunks_collection
from app.documents import create_document, delete_document, list_documents


def test_delete_document_removes_record_and_its_chunks(db):
    document = create_document(db, "u1", "s1", "a.pdf")
    chunks_collection(db).insert_many(
        [
            {"_id": "c1", "user_id": "u1", "subject_id": "s1", "document_id": document["_id"], "text": "x"},
            {"_id": "c2", "user_id": "u1", "subject_id": "s1", "document_id": "other-doc", "text": "y"},
        ]
    )

    assert delete_document(db, "u1", "s1", document["_id"]) is True

    assert list_documents(db, "u1", "s1") == []
    remaining = list(chunks_collection(db).find({}))
    assert [c["_id"] for c in remaining] == ["c2"]


def test_delete_document_returns_false_when_not_found(db):
    assert delete_document(db, "u1", "s1", "missing") is False


def test_delete_document_will_not_delete_another_users_document(db):
    document = create_document(db, "owner", "s1", "a.pdf")
    assert delete_document(db, "attacker", "s1", document["_id"]) is False
    assert len(list_documents(db, "owner", "s1")) == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_document_delete.py -v`
Expected: FAIL — `cannot import name 'delete_document'`.

- [ ] **Step 3: Add `delete_document` to `app/documents.py`**

Update the db import to include `chunks_collection`, then add the function after `mark_document`:

```python
from app.db import chunks_collection, documents_collection, get_db
```

```python
def delete_document(db: Database, user_id: str, subject_id: str, document_id: str) -> bool:
    """Delete a document and its embedded chunks.

    Chunks must go too — a deleted document whose chunks remained would still
    surface in retrieved answers.
    """
    result = documents_collection(db).delete_one(
        {"_id": document_id, "user_id": user_id, "subject_id": subject_id}
    )
    if result.deleted_count == 0:
        return False
    chunks_collection(db).delete_many(
        {"user_id": user_id, "subject_id": subject_id, "document_id": document_id}
    )
    return True
```

- [ ] **Step 4: Run the delete test**

Run: `.venv/Scripts/python -m pytest tests/test_document_delete.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing documents API test**

```python
# tests/test_api_documents.py
import io
from unittest.mock import patch

import pytest


@pytest.fixture
def subject(client, db):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    subject_id = client.post("/api/subjects", json={"name": "Physics"}).json()["subject"]["id"]
    return client, subject_id


def test_list_documents_starts_empty(subject):
    client, subject_id = subject
    response = client.get(f"/api/subjects/{subject_id}/documents")
    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_upload_returns_202_and_processing_status(subject):
    client, subject_id = subject
    with patch("app.api.documents.process_document") as mock_process:
        response = client.post(
            f"/api/subjects/{subject_id}/documents",
            files={"file": ("notes.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
    assert response.status_code == 202
    assert response.json()["document"]["status"] == "processing"
    assert response.json()["document"]["filename"] == "notes.pdf"
    mock_process.assert_called_once()


def test_uploaded_document_then_appears_in_the_list(subject):
    client, subject_id = subject
    with patch("app.api.documents.process_document"):
        client.post(
            f"/api/subjects/{subject_id}/documents",
            files={"file": ("notes.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
    documents = client.get(f"/api/subjects/{subject_id}/documents").json()["documents"]
    assert len(documents) == 1
    assert documents[0]["filename"] == "notes.pdf"


def test_upload_rejects_unsupported_file_type(subject):
    client, subject_id = subject
    response = client.post(
        f"/api/subjects/{subject_id}/documents",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_to_someone_elses_subject_returns_404(client, db):
    from app.subjects import create_subject

    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    other = create_subject(db, "someone-else", "Not Yours")
    response = client.post(
        f"/api/subjects/{other['_id']}/documents",
        files={"file": ("notes.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert response.status_code == 404


def test_delete_document(subject):
    client, subject_id = subject
    with patch("app.api.documents.process_document"):
        upload = client.post(
            f"/api/subjects/{subject_id}/documents",
            files={"file": ("notes.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
    document_id = upload.json()["document"]["id"]

    assert client.delete(f"/api/subjects/{subject_id}/documents/{document_id}").status_code == 204
    assert client.get(f"/api/subjects/{subject_id}/documents").json()["documents"] == []


def test_delete_missing_document_returns_404(subject):
    client, subject_id = subject
    assert client.delete(f"/api/subjects/{subject_id}/documents/nope").status_code == 404


def test_documents_require_authentication(client):
    assert client.get("/api/subjects/any/documents").status_code == 401
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_documents.py -v`
Expected: FAIL — 404s, the routes do not exist.

- [ ] **Step 7: Write `app/api/documents.py`**

```python
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from pymongo.database import Database

from app.api.deps import api_current_user
from app.db import get_db
from app.documents import create_document, delete_document, list_documents, process_document, save_upload
from app.extraction import DOCX_MIME, PPTX_MIME
from app.serializers import serialize_document
from app.subjects import get_subject

router = APIRouter(prefix="/api/subjects/{subject_id}/documents", tags=["documents"])

ACCEPTED_TYPES = {"application/pdf", DOCX_MIME, PPTX_MIME}


def _accepts(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type in ACCEPTED_TYPES or content_type.startswith("image/")


def _require_subject(db: Database, user_id: str, subject_id: str) -> dict:
    subject = get_subject(db, user_id, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("")
def list_route(
    subject_id: str, db: Database = Depends(get_db), user: dict = Depends(api_current_user)
):
    _require_subject(db, user["_id"], subject_id)
    return {"documents": [serialize_document(d) for d in list_documents(db, user["_id"], subject_id)]}


@router.post("", status_code=202)
def upload_route(
    subject_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
    user: dict = Depends(api_current_user),
):
    _require_subject(db, user["_id"], subject_id)
    if not _accepts(file.content_type):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Upload a PDF, DOCX, PPTX, or image.",
        )
    document = create_document(db, user["_id"], subject_id, file.filename)
    path = save_upload(user["_id"], subject_id, document["_id"], file)
    background_tasks.add_task(
        process_document,
        db,
        user["_id"],
        subject_id,
        document["_id"],
        path,
        file.content_type,
        file.filename,
    )
    return {"document": serialize_document(document)}


@router.delete("/{document_id}", status_code=204)
def delete_route(
    subject_id: str,
    document_id: str,
    db: Database = Depends(get_db),
    user: dict = Depends(api_current_user),
):
    _require_subject(db, user["_id"], subject_id)
    if not delete_document(db, user["_id"], subject_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(status_code=204)
```

Note on the mock target: the tests patch `app.api.documents.process_document`, not `app.documents.process_document`. `from app.documents import process_document` binds the function into this module's namespace at import time, so patching it on the source module would leave this reference untouched and the real pipeline would run against Gemini during tests.

- [ ] **Step 8: Include the router in `app/main.py`**

```python
from app.api.documents import router as api_documents_router
...
app.include_router(api_documents_router)
```

- [ ] **Step 9: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_api_documents.py tests/test_document_delete.py -v`
Expected: PASS (11 tests).

- [ ] **Step 10: Commit**

```bash
git add app/documents.py app/api/documents.py app/main.py tests/test_api_documents.py tests/test_document_delete.py
git commit -m "feat: add documents JSON API with upload validation and chunk-aware delete"
```

---

### Task 5: Chat API and persisting `found`

**Files:**
- Modify: `app/chat.py` (persist `found`)
- Create: `app/api/chat.py`
- Modify: `app/main.py` (include router)
- Test: `tests/test_chat.py` (extend), `tests/test_api_chat.py`

**Interfaces:**
- Consumes: `app.chat.save_chat_message/list_chat_history`, `app.rag_chain.answer_question/answer_general`, `app.subjects.get_subject`, `app.api.deps.api_current_user`, `app.serializers.serialize_message`.
- Produces: router at `/api/subjects/{subject_id}/messages`; saved chat messages now include `found: bool`.

- [ ] **Step 1: Add the failing `found` test to `tests/test_chat.py`**

Append:

```python
def test_save_chat_message_persists_the_found_flag(db):
    missing = {"answer": "Not found in your uploaded material.", "citations": [],
               "response_mode": "rag", "found": False}
    message = save_chat_message(db, "u1", "s1", "q", missing)
    assert message["found"] is False

    stored = list_chat_history(db, "u1", "s1")[0]
    assert stored["found"] is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_chat.py::test_save_chat_message_persists_the_found_flag -v`
Expected: FAIL — `KeyError: 'found'`.

- [ ] **Step 3: Persist `found` in `app/chat.py`**

In `save_chat_message`, add the field to the stored document:

```python
    message = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "subject_id": subject_id,
        "question": question,
        "answer": result["answer"],
        "citations": result["citations"],
        "response_mode": result["response_mode"],
        "found": result["found"],
        "created_at": datetime.now(timezone.utc),
    }
```

- [ ] **Step 4: Run the chat tests**

Run: `.venv/Scripts/python -m pytest tests/test_chat.py -v`
Expected: PASS (5 tests). The existing tests already pass `found` in their result dicts.

- [ ] **Step 5: Write the failing chat API test**

```python
# tests/test_api_chat.py
from unittest.mock import patch

import pytest


@pytest.fixture
def subject(client):
    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    subject_id = client.post("/api/subjects", json={"name": "Physics"}).json()["subject"]["id"]
    return client, subject_id


GROUNDED = {
    "answer": "V = IR",
    "citations": [{"filename": "ohms_law.pdf", "source_label": "page 1"}],
    "response_mode": "rag",
    "found": True,
}
MISSING = {"answer": "Not found in your uploaded material.", "citations": [],
           "response_mode": "rag", "found": False}
GENERAL = {"answer": "Paris", "citations": [], "response_mode": "general", "found": True}


def test_messages_start_empty(subject):
    client, subject_id = subject
    response = client.get(f"/api/subjects/{subject_id}/messages")
    assert response.status_code == 200
    assert response.json() == {"messages": []}


def test_ask_returns_grounded_message_with_citations(subject):
    client, subject_id = subject
    with patch("app.api.chat.answer_question", return_value=GROUNDED):
        response = client.post(f"/api/subjects/{subject_id}/messages", json={"question": "What is Ohm's Law?"})

    assert response.status_code == 200
    message = response.json()["message"]
    assert message["response_mode"] == "rag"
    assert message["found"] is True
    assert message["citations"] == [{"filename": "ohms_law.pdf", "source_label": "page 1"}]


def test_ask_records_not_found(subject):
    client, subject_id = subject
    with patch("app.api.chat.answer_question", return_value=MISSING):
        message = client.post(
            f"/api/subjects/{subject_id}/messages", json={"question": "Capital of France?"}
        ).json()["message"]

    assert message["found"] is False
    assert message["citations"] == []


def test_general_answer_is_tagged_and_uncited(subject):
    client, subject_id = subject
    with patch("app.api.chat.answer_general", return_value=GENERAL):
        message = client.post(
            f"/api/subjects/{subject_id}/messages/general", json={"question": "Capital of France?"}
        ).json()["message"]

    assert message["response_mode"] == "general"
    assert message["citations"] == []


def test_history_returns_messages_oldest_first(subject):
    client, subject_id = subject
    with patch("app.api.chat.answer_question", return_value=GROUNDED):
        client.post(f"/api/subjects/{subject_id}/messages", json={"question": "first"})
    with patch("app.api.chat.answer_general", return_value=GENERAL):
        client.post(f"/api/subjects/{subject_id}/messages/general", json={"question": "second"})

    messages = client.get(f"/api/subjects/{subject_id}/messages").json()["messages"]
    assert [m["question"] for m in messages] == ["first", "second"]


def test_blank_question_is_rejected(subject):
    client, subject_id = subject
    assert client.post(f"/api/subjects/{subject_id}/messages", json={"question": "  "}).status_code == 422


def test_asking_in_someone_elses_subject_returns_404(client, db):
    from app.subjects import create_subject

    client.post("/api/auth/signup", json={"email": "s@e.com", "password": "password123"})
    other = create_subject(db, "someone-else", "Not Yours")
    with patch("app.api.chat.answer_question", return_value=GROUNDED):
        response = client.post(f"/api/subjects/{other['_id']}/messages", json={"question": "q"})
    assert response.status_code == 404


def test_messages_require_authentication(client):
    assert client.get("/api/subjects/any/messages").status_code == 401
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api_chat.py -v`
Expected: FAIL — 404s, the routes do not exist.

- [ ] **Step 7: Write `app/api/chat.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from app.api.deps import api_current_user
from app.chat import list_chat_history, save_chat_message
from app.db import get_db
from app.rag_chain import answer_general, answer_question
from app.serializers import serialize_message
from app.subjects import get_subject

router = APIRouter(prefix="/api/subjects/{subject_id}/messages", tags=["chat"])


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question cannot be blank")
        return cleaned


def _require_subject(db: Database, user_id: str, subject_id: str) -> dict:
    subject = get_subject(db, user_id, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("")
def history_route(
    subject_id: str, db: Database = Depends(get_db), user: dict = Depends(api_current_user)
):
    _require_subject(db, user["_id"], subject_id)
    return {"messages": [serialize_message(m) for m in list_chat_history(db, user["_id"], subject_id)]}


@router.post("")
def ask_route(
    subject_id: str,
    payload: Question,
    db: Database = Depends(get_db),
    user: dict = Depends(api_current_user),
):
    _require_subject(db, user["_id"], subject_id)
    result = answer_question(db, user["_id"], subject_id, payload.question)
    message = save_chat_message(db, user["_id"], subject_id, payload.question, result)
    return {"message": serialize_message(message)}


@router.post("/general")
def ask_general_route(
    subject_id: str,
    payload: Question,
    db: Database = Depends(get_db),
    user: dict = Depends(api_current_user),
):
    _require_subject(db, user["_id"], subject_id)
    result = answer_general(payload.question)
    message = save_chat_message(db, user["_id"], subject_id, payload.question, result)
    return {"message": serialize_message(message)}
```

- [ ] **Step 8: Include the router in `app/main.py`**

```python
from app.api.chat import router as api_chat_router
...
app.include_router(api_chat_router)
```

- [ ] **Step 9: Run the full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS — all tests, backend API layer complete.

- [ ] **Step 10: Commit**

```bash
git add app/chat.py app/api/chat.py app/main.py tests/test_api_chat.py tests/test_chat.py
git commit -m "feat: add chat JSON API and persist the found flag on messages"
```

---

### Task 6: Vite + React scaffold with design tokens

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/.gitignore`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/vite-env.d.ts`
- Create: `frontend/src/styles/tokens.css`, `frontend/src/styles/base.css`
- Modify: `.gitignore` (ignore `frontend/node_modules`, `frontend/dist`)

**Interfaces:**
- Produces: a running dev server on `http://localhost:5173` proxying `/api` to `http://127.0.0.1:8000`; the token stylesheet every later task's CSS depends on.

- [ ] **Step 1: Scaffold the project**

```bash
cd "C:/Users/Unnati Bhawsar/Desktop/project1-exam_partner"
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router-dom @tanstack/react-query
npm install @fontsource-variable/instrument-sans @fontsource/ibm-plex-mono
npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom msw
```

- [ ] **Step 2: Delete the scaffold's demo files**

```bash
rm frontend/src/App.css frontend/src/index.css frontend/src/assets/react.svg
```

- [ ] **Step 3: Write `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxying keeps the browser on one origin: no CORS, and the session
    // cookie behaves in dev exactly as it will in production.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
```

Add the Vitest types reference at the top of `frontend/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
/// <reference types="vitest" />
```

- [ ] **Step 4: Write `frontend/src/styles/tokens.css`**

This is the approved palette. Every other stylesheet reads from it.

```css
:root {
  --paper: #ffffff;
  --wash: #faf9f7;
  --wash-2: #f4f3f0;
  --line: #e7e5e1;
  --line-strong: #d6d3cd;
  --ink: #0c0c0d;
  --ink-2: #5b5b60;
  --ink-3: #97969c;

  --ok: #3f7d5c;
  --wait: #9a7328;
  --err: #a8453e;

  --r: 8px;
  --r-sm: 6px;
  --shadow-menu: 0 8px 28px rgba(12, 12, 13, 0.09);

  --sans: "Instrument Sans Variable", -apple-system, "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}

@media (prefers-color-scheme: dark) {
  :root {
    --paper: #0e0e0f;
    --wash: #161617;
    --wash-2: #1d1d1f;
    --line: #262628;
    --line-strong: #37373a;
    --ink: #f5f4f2;
    --ink-2: #a3a2a6;
    --ink-3: #6e6d73;
    --ok: #6fbf92;
    --wait: #d6a85a;
    --err: #de8a83;
    --shadow-menu: 0 8px 28px rgba(0, 0, 0, 0.5);
  }
}

:root[data-theme="dark"] {
  --paper: #0e0e0f;
  --wash: #161617;
  --wash-2: #1d1d1f;
  --line: #262628;
  --line-strong: #37373a;
  --ink: #f5f4f2;
  --ink-2: #a3a2a6;
  --ink-3: #6e6d73;
  --ok: #6fbf92;
  --wait: #d6a85a;
  --err: #de8a83;
  --shadow-menu: 0 8px 28px rgba(0, 0, 0, 0.5);
}

:root[data-theme="light"] {
  --paper: #ffffff;
  --wash: #faf9f7;
  --wash-2: #f4f3f0;
  --line: #e7e5e1;
  --line-strong: #d6d3cd;
  --ink: #0c0c0d;
  --ink-2: #5b5b60;
  --ink-3: #97969c;
  --ok: #3f7d5c;
  --wait: #9a7328;
  --err: #a8453e;
  --shadow-menu: 0 8px 28px rgba(12, 12, 13, 0.09);
}
```

- [ ] **Step 5: Write `frontend/src/styles/base.css`**

```css
* {
  box-sizing: border-box;
}

html,
body,
#root {
  margin: 0;
  padding: 0;
  min-height: 100%;
}

body {
  font-family: var(--sans);
  background: var(--paper);
  color: var(--ink);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

h1,
h2,
h3 {
  margin: 0;
  font-weight: 600;
  letter-spacing: -0.018em;
  text-wrap: balance;
}

a {
  color: inherit;
}

button {
  font-family: inherit;
}

:focus-visible {
  outline: 1.5px solid var(--ink);
  outline-offset: 2px;
  border-radius: 3px;
}

.mono {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 500;
}
```

- [ ] **Step 6: Write `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";

import "@fontsource-variable/instrument-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";

import "./styles/tokens.css";
import "./styles/base.css";

import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 7: Write a placeholder `frontend/src/App.tsx`**

Task 16 replaces this with the real router.

```tsx
export default function App() {
  return <h1>Exam Partner</h1>;
}
```

- [ ] **Step 8: Set `frontend/index.html` title**

Replace the `<title>` line with:

```html
    <title>Exam Partner</title>
```

- [ ] **Step 9: Ignore build artifacts**

Append to the repo-root `.gitignore`:

```
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 10: Verify the dev server boots**

```bash
cd frontend && npm run dev
```
Expected: Vite serves on `http://localhost:5173` and the page shows "Exam Partner". Stop it with Ctrl+C.

- [ ] **Step 11: Commit**

```bash
git add frontend .gitignore
git commit -m "feat: scaffold React frontend with Vite, design tokens, and API dev proxy"
```

---

### Task 7: API client, shared types, and auth context

**Files:**
- Create: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
- Create: `frontend/src/auth/AuthContext.tsx`, `frontend/src/auth/ProtectedRoute.tsx`
- Create: `frontend/src/test/setup.ts`, `frontend/src/test/server.ts`
- Test: `frontend/src/auth/AuthContext.test.tsx`

**Interfaces:**
- Produces:
  - `ApiError` (class with `status: number`, `detail: string`)
  - `api.get<T>(path)`, `api.post<T>(path, body?)`, `api.patch<T>(path, body)`, `api.del(path)`, `api.upload<T>(path, file)`
  - `AuthProvider`, `useAuth() -> { user, status, login, signup, logout }` where `status` is `"loading" | "authenticated" | "anonymous"`
  - `ProtectedRoute` component
  - Types `User`, `Subject`, `SubjectSummary`, `Doc`, `Citation`, `Message`

- [ ] **Step 1: Write `frontend/src/lib/types.ts`**

```ts
export type User = { id: string; email: string };

export type Subject = { id: string; name: string; created_at: string | null };

export type SubjectSummary = Subject & {
  document_count: number;
  processing_count: number;
  failed_count: number;
  last_asked_at: string | null;
};

export type DocStatus = "processing" | "ready" | "failed";

export type Doc = {
  id: string;
  filename: string;
  status: DocStatus;
  error: string | null;
  created_at: string | null;
};

export type Citation = { filename: string; source_label: string };

export type Message = {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  response_mode: "rag" | "general";
  found: boolean;
  created_at: string | null;
};
```

- [ ] **Step 2: Write `frontend/src/lib/api.ts`**

```ts
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};

  if (!response.ok) {
    // FastAPI validation errors put a list in `detail`; flatten to one line.
    const raw = payload.detail;
    const detail = Array.isArray(raw)
      ? raw.map((d: { msg?: string }) => d.msg ?? "Invalid value").join(", ")
      : typeof raw === "string"
        ? raw
        : "Something went wrong";
    throw new ApiError(response.status, detail);
  }

  return payload as T;
}

function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return fetch(path, { credentials: "include", ...init }).then((r) => parse<T>(r));
}

function withJson(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, withJson("POST", body)),
  patch: <T,>(path: string, body: unknown) => request<T>(path, withJson("PATCH", body)),
  del: (path: string) => request<void>(path, { method: "DELETE" }),
  upload: <T,>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
};
```

- [ ] **Step 3: Write `frontend/src/test/setup.ts` and `frontend/src/test/server.ts`**

```ts
// src/test/server.ts
import { setupServer } from "msw/node";

export const server = setupServer();
```

```ts
// src/test/setup.ts
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 4: Write the failing auth context test**

```tsx
// src/auth/AuthContext.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../test/server";
import { AuthProvider, useAuth } from "./AuthContext";

function Probe() {
  const { user, status, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="email">{user?.email ?? "none"}</span>
      <button onClick={() => logout()}>Log out</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

describe("AuthProvider", () => {
  it("starts in loading and becomes authenticated when the session is valid", async () => {
    server.use(
      http.get("/api/auth/me", () =>
        HttpResponse.json({ user: { id: "u1", email: "s@e.com" } }),
      ),
    );

    renderProbe();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("email")).toHaveTextContent("s@e.com");
  });

  it("becomes anonymous when the session check returns 401", async () => {
    server.use(
      http.get("/api/auth/me", () =>
        HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
      ),
    );

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(screen.getByTestId("email")).toHaveTextContent("none");
  });

  it("clears the user on logout", async () => {
    server.use(
      http.get("/api/auth/me", () =>
        HttpResponse.json({ user: { id: "u1", email: "s@e.com" } }),
      ),
      http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })),
    );

    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });
});
```

- [ ] **Step 5: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/auth/AuthContext.test.tsx
```
Expected: FAIL — cannot resolve `./AuthContext`.

- [ ] **Step 6: Write `frontend/src/auth/AuthContext.tsx`**

```tsx
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, api } from "../lib/api";
import type { User } from "../lib/types";

type Status = "loading" | "authenticated" | "anonymous";

type AuthValue = {
  user: User | null;
  status: Status;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  // Restore the session on load so a refresh does not log the user out.
  useEffect(() => {
    let cancelled = false;
    api
      .get<{ user: User }>("/api/auth/me")
      .then((data) => {
        if (cancelled) return;
        setUser(data.user);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        setUser(null);
        setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const authenticate = useCallback(async (path: string, email: string, password: string) => {
    const data = await api.post<{ user: User }>(path, { email, password });
    setUser(data.user);
    setStatus("authenticated");
  }, []);

  const login = useCallback(
    (email: string, password: string) => authenticate("/api/auth/login", email, password),
    [authenticate],
  );

  const signup = useCallback(
    (email: string, password: string) => authenticate("/api/auth/signup", email, password),
    [authenticate],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } catch (error) {
      // A 401 here means the session was already gone — the goal is met either way.
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
    }
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo(
    () => ({ user, status, login, signup, logout }),
    [user, status, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
```

- [ ] **Step 7: Write `frontend/src/auth/ProtectedRoute.tsx`**

```tsx
import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "./AuthContext";

export default function ProtectedRoute() {
  const { status } = useAuth();

  // Render nothing while the session check is in flight, so an authenticated
  // user never sees a flash of the login screen on refresh.
  if (status === "loading") return null;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  return <Outlet />;
}
```

- [ ] **Step 8: Run the tests**

```bash
cd frontend && npx vitest run src/auth/AuthContext.test.tsx
```
Expected: PASS (3 tests).

- [ ] **Step 9: Commit**

```bash
git add frontend/src
git commit -m "feat: add API client, shared types, and session-restoring auth context"
```

---

### Task 8: UI primitives

**Files:**
- Create: `frontend/src/styles/components.css`
- Create: `frontend/src/components/Button.tsx`, `Field.tsx`, `StatusDot.tsx`, `Card.tsx`
- Modify: `frontend/src/main.tsx` (import the stylesheet)

**Interfaces:**
- Produces:
  - `<Button variant="solid" | "outline" size="md" | "sm" {...buttonProps} />`
  - `<Field label="Email" id="email" error?: string {...inputProps} />`
  - `<StatusDot tone="ok" | "wait" | "err" label?: string />`
  - `<Card>`, `<CardHead left={ReactNode} right?: ReactNode />`

- [ ] **Step 1: Write `frontend/src/styles/components.css`**

```css
.btn {
  appearance: none;
  cursor: pointer;
  border: 1px solid transparent;
  font-weight: 500;
  font-size: 13.5px;
  letter-spacing: -0.005em;
  padding: 9px 16px;
  border-radius: 7px;
  transition:
    background 0.12s,
    border-color 0.12s,
    color 0.12s;
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.btn-solid {
  background: var(--ink);
  color: var(--paper);
}
.btn-solid:hover:not(:disabled) {
  background: var(--ink-2);
}
.btn-outline {
  background: var(--paper);
  color: var(--ink);
  border-color: var(--line-strong);
}
.btn-outline:hover:not(:disabled) {
  border-color: var(--ink);
  background: var(--wash);
}
.btn-sm {
  padding: 6px 12px;
  font-size: 12.5px;
  border-radius: var(--r-sm);
}
.btn-block {
  width: 100%;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.field label {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-2);
  font-weight: 500;
}
.field input {
  font: inherit;
  font-size: 14px;
  padding: 11px 13px;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: var(--paper);
  color: var(--ink);
  transition:
    border-color 0.12s,
    box-shadow 0.12s;
}
.field input:focus {
  outline: none;
  border-color: var(--ink);
  box-shadow: 0 0 0 3px var(--wash-2);
}
.field input::placeholder {
  color: var(--ink-3);
}
.field-error {
  font-size: 12px;
  color: var(--err);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  font-weight: 500;
}
.status .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.st-ok {
  color: var(--ok);
}
.st-wait {
  color: var(--wait);
}
.st-err {
  color: var(--err);
}

.card {
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--paper);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 15px;
  border-bottom: 1px solid var(--line);
}
.card-head .mono {
  font-size: 10px;
  letter-spacing: 0.09em;
}
```

- [ ] **Step 2: Write `frontend/src/components/Button.tsx`**

```tsx
import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "solid" | "outline";
  size?: "md" | "sm";
  block?: boolean;
};

export default function Button({
  variant = "solid",
  size = "md",
  block = false,
  className = "",
  ...rest
}: Props) {
  const classes = [
    "btn",
    `btn-${variant}`,
    size === "sm" ? "btn-sm" : "",
    block ? "btn-block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <button className={classes} {...rest} />;
}
```

- [ ] **Step 3: Write `frontend/src/components/Field.tsx`**

```tsx
import type { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  error?: string;
};

export default function Field({ id, label, error, ...rest }: Props) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} aria-invalid={error ? true : undefined} {...rest} />
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/StatusDot.tsx`**

```tsx
type Tone = "ok" | "wait" | "err";

const TONE_CLASS: Record<Tone, string> = {
  ok: "st-ok",
  wait: "st-wait",
  err: "st-err",
};

export default function StatusDot({ tone, label }: { tone: Tone; label?: string }) {
  return (
    <span className={`status ${TONE_CLASS[tone]}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
```

- [ ] **Step 5: Write `frontend/src/components/Card.tsx`**

```tsx
import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`.trim()}>{children}</div>;
}

export function CardHead({ left, right }: { left: ReactNode; right?: ReactNode }) {
  return (
    <div className="card-head">
      <span className="mono">{left}</span>
      {right ? <span className="mono">{right}</span> : null}
    </div>
  );
}
```

- [ ] **Step 6: Import the stylesheet in `frontend/src/main.tsx`**

Add after the `base.css` import:

```tsx
import "./styles/components.css";
```

- [ ] **Step 7: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: add Button, Field, StatusDot, and Card primitives"
```

---

### Task 9: App shell — sidebar, topbar, session menu

**Files:**
- Create: `frontend/src/styles/layout.css`
- Create: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/main.tsx` (import the stylesheet)
- Test: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: `useAuth` from Task 7.
- Produces: `<AppShell breadcrumb={ReactNode} sidebarExtra?: ReactNode>{children}</AppShell>` — renders the sidebar, topbar with breadcrumb and session menu, and a padded content area.

- [ ] **Step 1: Write `frontend/src/styles/layout.css`**

```css
.app {
  display: grid;
  grid-template-columns: 224px 1fr;
  min-height: 100vh;
}

.side {
  border-right: 1px solid var(--line);
  padding: 18px 12px;
  display: flex;
  flex-direction: column;
  gap: 26px;
  background: var(--paper);
}
.side-logo {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 2px 8px;
  text-decoration: none;
}
.side-logo .mark {
  width: 24px;
  height: 24px;
  border-radius: var(--r-sm);
  background: var(--ink);
  color: var(--paper);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--mono);
}
.side-logo .name {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: -0.015em;
}
.side-sec {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.side-sec .mono {
  padding: 0 8px 7px;
  font-size: 10px;
  letter-spacing: 0.09em;
}
.side-link {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 9px;
  border-radius: var(--r-sm);
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink-2);
  text-decoration: none;
  cursor: pointer;
}
.side-link .sq {
  width: 6px;
  height: 6px;
  border-radius: 2px;
  background: var(--line-strong);
  flex-shrink: 0;
}
.side-link:hover {
  background: var(--wash);
  color: var(--ink);
}
.side-link.on {
  background: var(--wash-2);
  color: var(--ink);
  font-weight: 600;
}
.side-link.on .sq {
  background: var(--ink);
}
.side-foot {
  margin-top: auto;
}

.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--paper);
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 26px;
  height: 53px;
  border-bottom: 1px solid var(--line);
  background: var(--paper);
}
.bread {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-3);
}
.bread a {
  text-decoration: none;
}
.bread a:hover {
  color: var(--ink);
}
.bread .now {
  color: var(--ink);
  font-weight: 600;
}

.sess {
  position: relative;
  display: flex;
  align-items: center;
}
.who {
  width: 29px;
  height: 29px;
  border-radius: 50%;
  background: var(--ink);
  color: var(--paper);
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--mono);
  border: none;
  padding: 0;
}
.sess-menu {
  position: absolute;
  top: 38px;
  right: 0;
  width: 216px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 5px;
  box-shadow: var(--shadow-menu);
  z-index: 20;
}
.sess-id {
  padding: 9px 10px 10px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 4px;
}
.sess-id .n {
  font-weight: 600;
  font-size: 13px;
}
.sess-id .e {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-3);
  margin-top: 2px;
  word-break: break-all;
}
.sess-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 7px 10px;
  border-radius: var(--r-sm);
  font-size: 13px;
  color: var(--ink-2);
  cursor: pointer;
  background: none;
  border: none;
  text-align: left;
  font-family: inherit;
}
.sess-item:hover {
  background: var(--wash);
  color: var(--ink);
}

.body-pad {
  padding: 30px 26px;
  flex: 1;
}

@media (max-width: 940px) {
  .app {
    grid-template-columns: 1fr;
  }
  .side {
    display: none;
  }
}
```

- [ ] **Step 2: Write the failing test**

```tsx
// src/components/AppShell.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { server } from "../test/server";
import AppShell from "./AppShell";

function renderShell() {
  server.use(
    http.get("/api/auth/me", () => HttpResponse.json({ user: { id: "u1", email: "rudra@e.com" } })),
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <AppShell breadcrumb={<span className="now">Subjects</span>}>
          <p>Page body</p>
        </AppShell>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  it("renders the breadcrumb and page body", async () => {
    renderShell();
    expect(screen.getByText("Subjects")).toBeInTheDocument();
    expect(screen.getByText("Page body")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /account menu/i })).toBeInTheDocument());
  });

  it("shows the signed-in email only after opening the session menu", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByRole("button", { name: /account menu/i })).toBeInTheDocument());

    expect(screen.queryByText("rudra@e.com")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.getByText("rudra@e.com")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/components/AppShell.test.tsx
```
Expected: FAIL — cannot resolve `./AppShell`.

- [ ] **Step 4: Write `frontend/src/components/AppShell.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

type Props = {
  breadcrumb: ReactNode;
  sidebarExtra?: ReactNode;
  children: ReactNode;
};

export default function AppShell({ breadcrumb, sidebarExtra, children }: Props) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const sessionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDocumentClick(event: MouseEvent) {
      if (!sessionRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, [menuOpen]);

  const initials = (user?.email ?? "?").slice(0, 2).toUpperCase();

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app">
      <aside className="side">
        <Link className="side-logo" to="/subjects">
          <span className="mark">K</span>
          <span className="name">Exam Partner</span>
        </Link>
        <div className="side-sec">
          <div className="mono">Library</div>
          <Link className="side-link on" to="/subjects">
            <span className="sq" /> Subjects
          </Link>
        </div>
        {sidebarExtra ? <div className="side-foot side-sec">{sidebarExtra}</div> : null}
      </aside>

      <div className="main">
        <div className="top">
          <div className="bread">{breadcrumb}</div>
          <div className="sess" ref={sessionRef}>
            <button
              className="who"
              aria-label="Account menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              {initials}
            </button>
            {menuOpen ? (
              <div className="sess-menu">
                <div className="sess-id">
                  <div className="n">Signed in</div>
                  <div className="e">{user?.email}</div>
                </div>
                <button className="sess-item" onClick={onLogout}>
                  Log out
                </button>
              </div>
            ) : null}
          </div>
        </div>
        <div className="body-pad">{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Import the stylesheet in `frontend/src/main.tsx`**

```tsx
import "./styles/layout.css";
```

- [ ] **Step 6: Run the tests**

```bash
cd frontend && npx vitest run src/components/AppShell.test.tsx
```
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: add app shell with sidebar, breadcrumb topbar, and session menu"
```

---

### Task 10: Login and signup pages

**Files:**
- Create: `frontend/src/styles/pages.css`
- Create: `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/SignupPage.tsx`
- Modify: `frontend/src/main.tsx` (import the stylesheet)
- Test: `frontend/src/pages/LoginPage.test.tsx`

**Interfaces:**
- Consumes: `useAuth`, `Button`, `Field`, `ApiError`.
- Produces: `LoginPage`, `SignupPage` route components.

- [ ] **Step 1: Create `frontend/src/styles/pages.css` with the auth block**

Later tasks append to this file.

```css
/* ---------- auth ---------- */
.auth-wrap {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 40px 24px;
  background: var(--paper);
}
.auth-inner {
  width: 100%;
  max-width: 352px;
}
.auth-logo {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 40px;
}
.auth-logo .mark {
  width: 26px;
  height: 26px;
  border-radius: var(--r-sm);
  background: var(--ink);
  color: var(--paper);
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--mono);
}
.auth-logo .name {
  font-weight: 600;
  font-size: 14.5px;
  letter-spacing: -0.015em;
}
.auth-inner h1 {
  font-size: 25px;
  margin-bottom: 6px;
  letter-spacing: -0.028em;
}
.auth-inner .lede {
  color: var(--ink-2);
  font-size: 14px;
  margin: 0 0 30px;
}
.auth-inner form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.auth-error {
  font-size: 13px;
  color: var(--err);
  margin: 0;
}
.auth-alt {
  margin-top: 26px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  font-size: 13.5px;
  color: var(--ink-2);
  text-align: center;
}
.auth-alt a {
  font-weight: 600;
  text-decoration: none;
  border-bottom: 1px solid var(--line-strong);
  padding-bottom: 1px;
}
.auth-alt a:hover {
  border-color: var(--ink);
}
.auth-note {
  margin-top: 34px;
  padding: 14px 15px;
  background: var(--wash);
  border: 1px solid var(--line);
  border-radius: var(--r);
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--ink-2);
}
.auth-note strong {
  color: var(--ink);
  font-weight: 600;
}
```

- [ ] **Step 2: Write the failing login test**

```tsx
// src/pages/LoginPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { server } from "../test/server";
import LoginPage from "./LoginPage";

function renderLogin() {
  server.use(
    http.get("/api/auth/me", () =>
      HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
    ),
  );
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/subjects" element={<h1>Subjects screen</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  it("logs in and navigates to subjects", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json({ user: { id: "u1", email: "s@e.com" } }),
      ),
    );
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "s@e.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(screen.getByText("Subjects screen")).toBeInTheDocument());
  });

  it("shows the server's message when credentials are wrong", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 }),
      ),
    );
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "s@e.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-pass");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/LoginPage.test.tsx
```
Expected: FAIL — cannot resolve `./LoginPage`.

- [ ] **Step 4: Write `frontend/src/pages/LoginPage.tsx`**

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import Button from "../components/Button";
import Field from "../components/Field";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      navigate("/subjects", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-inner">
        <div className="auth-logo">
          <span className="mark">K</span>
          <span className="name">Exam Partner</span>
        </div>
        <h1>Log in</h1>
        <p className="lede">Pick up where you left off.</p>
        <form onSubmit={onSubmit}>
          <Field
            id="email"
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error ? <p className="auth-error">{error}</p> : null}
          <Button type="submit" block disabled={busy}>
            {busy ? "Logging in…" : "Log in"}
          </Button>
        </form>
        <div className="auth-alt">
          No account yet? <Link to="/signup">Create one</Link>
        </div>
        <div className="auth-note">
          Your session stays signed in for 14 days on this device.{" "}
          <strong>Uploads and chats are private to your account</strong> — never shared across users.
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/src/pages/SignupPage.tsx`**

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import Button from "../components/Button";
import Field from "../components/Field";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../lib/api";

export default function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await signup(email, password);
      navigate("/subjects", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-inner">
        <div className="auth-logo">
          <span className="mark">K</span>
          <span className="name">Exam Partner</span>
        </div>
        <h1>Create your account</h1>
        <p className="lede">Answers from your own material — nothing else.</p>
        <form onSubmit={onSubmit}>
          <Field
            id="email"
            label="Email"
            type="email"
            autoComplete="email"
            required
            placeholder="you@college.edu"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            id="password"
            label="Password"
            type="password"
            autoComplete="new-password"
            required
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error ? <p className="auth-error">{error}</p> : null}
          <Button type="submit" block disabled={busy}>
            {busy ? "Creating account…" : "Create account"}
          </Button>
        </form>
        <div className="auth-alt">
          Already registered? <Link to="/login">Log in</Link>
        </div>
        <div className="auth-note">
          Upload textbooks, slides, and photos of handwritten notes. Every answer cites the{" "}
          <strong>file and page</strong> it came from.
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Import the stylesheet in `frontend/src/main.tsx`**

```tsx
import "./styles/pages.css";
```

- [ ] **Step 7: Run the tests**

```bash
cd frontend && npx vitest run src/pages/LoginPage.test.tsx
```
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: add login and signup pages"
```

---

### Task 11: Subjects page and table

**Files:**
- Create: `frontend/src/features/subjects/useSubjects.ts`, `frontend/src/features/subjects/SubjectsTable.tsx`
- Create: `frontend/src/pages/SubjectsPage.tsx`
- Modify: `frontend/src/styles/pages.css` (append the table block)
- Test: `frontend/src/features/subjects/SubjectsTable.test.tsx`

**Interfaces:**
- Consumes: `api`, `SubjectSummary`, `AppShell`, `StatusDot`, `Button`.
- Produces: `useSubjects()` (TanStack Query list), `useCreateSubject()` (mutation), `<SubjectsTable subjects={SubjectSummary[]} />`, `SubjectsPage`.

- [ ] **Step 1: Append the table styles to `frontend/src/styles/pages.css`**

```css
/* ---------- subjects table ---------- */
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 26px;
}
.page-head h1 {
  font-size: 21px;
  letter-spacing: -0.026em;
}
.page-head p {
  color: var(--ink-2);
  font-size: 13.5px;
  margin: 5px 0 0;
}

.tbl {
  border: 1px solid var(--line);
  border-radius: var(--r);
  overflow: hidden;
}
.tbl-head,
.tbl-row {
  display: grid;
  grid-template-columns: 1fr 108px 132px 116px 30px;
  align-items: center;
  gap: 14px;
  padding: 0 16px;
}
.tbl-head {
  height: 36px;
  background: var(--wash);
  border-bottom: 1px solid var(--line);
}
.tbl-head span {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 500;
}
.tbl-row {
  height: 56px;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.1s;
  background: none;
  border-left: none;
  border-right: none;
  border-top: none;
  width: 100%;
  text-align: left;
  font-family: inherit;
  color: inherit;
}
.tbl-row:last-child {
  border-bottom: none;
}
.tbl-row:hover {
  background: var(--wash);
}
.tbl-row .subj {
  font-weight: 600;
  font-size: 14.5px;
  letter-spacing: -0.012em;
}
.tbl-row .num {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.tbl-row .when {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
}
.tbl-row .go {
  color: var(--ink-3);
  font-size: 14px;
  text-align: right;
}
.tbl-row:hover .go {
  color: var(--ink);
}
.tbl-blank {
  padding: 26px 16px;
  text-align: center;
  color: var(--ink-3);
  font-size: 13.5px;
}

@media (max-width: 940px) {
  .tbl-head,
  .tbl-row {
    grid-template-columns: 1fr 80px 30px;
  }
  .tbl-head span:nth-child(3),
  .tbl-head span:nth-child(4),
  .tbl-row .when,
  .tbl-row .state {
    display: none;
  }
}
```

- [ ] **Step 2: Write the failing table test**

```tsx
// src/features/subjects/SubjectsTable.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { SubjectSummary } from "../../lib/types";
import SubjectsTable from "./SubjectsTable";

const READY: SubjectSummary = {
  id: "s1", name: "Physics", created_at: null,
  document_count: 3, processing_count: 0, failed_count: 0, last_asked_at: "2026-08-08T10:00:00+00:00",
};
const BUSY: SubjectSummary = { ...READY, id: "s2", name: "Thermo", processing_count: 1, last_asked_at: null };
const BROKEN: SubjectSummary = { ...READY, id: "s3", name: "Chem", failed_count: 2 };

function renderTable(subjects: SubjectSummary[], onOpen = vi.fn()) {
  render(
    <MemoryRouter>
      <SubjectsTable subjects={subjects} onOpen={onOpen} />
    </MemoryRouter>,
  );
  return onOpen;
}

describe("SubjectsTable", () => {
  it("shows an empty message when there are no subjects", () => {
    renderTable([]);
    expect(screen.getByText(/no subjects yet/i)).toBeInTheDocument();
  });

  it("summarises each subject's state", () => {
    renderTable([READY, BUSY, BROKEN]);
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("1 indexing")).toBeInTheDocument();
    expect(screen.getByText("2 failed")).toBeInTheDocument();
  });

  it("shows a dash when a subject has never been asked", () => {
    renderTable([BUSY]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("calls onOpen with the subject id when a row is clicked", async () => {
    const onOpen = renderTable([READY]);
    await userEvent.click(screen.getByRole("button", { name: /physics/i }));
    expect(onOpen).toHaveBeenCalledWith("s1");
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/features/subjects/SubjectsTable.test.tsx
```
Expected: FAIL — cannot resolve `./SubjectsTable`.

- [ ] **Step 4: Write `frontend/src/features/subjects/SubjectsTable.tsx`**

```tsx
import StatusDot from "../../components/StatusDot";
import type { SubjectSummary } from "../../lib/types";

function relativeDay(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 30) return "Last week";
  return then.toLocaleDateString();
}

function State({ subject }: { subject: SubjectSummary }) {
  if (subject.failed_count > 0) {
    return <StatusDot tone="err" label={`${subject.failed_count} failed`} />;
  }
  if (subject.processing_count > 0) {
    return <StatusDot tone="wait" label={`${subject.processing_count} indexing`} />;
  }
  if (subject.document_count === 0) {
    return <StatusDot tone="wait" label="No sources" />;
  }
  return <StatusDot tone="ok" label="Ready" />;
}

type Props = {
  subjects: SubjectSummary[];
  onOpen: (subjectId: string) => void;
};

export default function SubjectsTable({ subjects, onOpen }: Props) {
  return (
    <div className="tbl">
      <div className="tbl-head">
        <span>Subject</span>
        <span>Documents</span>
        <span>Last asked</span>
        <span>Status</span>
        <span />
      </div>

      {subjects.length === 0 ? (
        <div className="tbl-blank">No subjects yet. Create one to start uploading material.</div>
      ) : (
        subjects.map((subject) => (
          <button key={subject.id} className="tbl-row" onClick={() => onOpen(subject.id)}>
            <div className="subj">{subject.name}</div>
            <div className="num">{subject.document_count}</div>
            <div className="when">{relativeDay(subject.last_asked_at)}</div>
            <div className="state">
              <State subject={subject} />
            </div>
            <div className="go">→</div>
          </button>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/src/features/subjects/useSubjects.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/api";
import type { Subject, SubjectSummary } from "../../lib/types";

export const subjectsKey = ["subjects"] as const;

export function useSubjects() {
  return useQuery({
    queryKey: subjectsKey,
    queryFn: () => api.get<{ subjects: SubjectSummary[] }>("/api/subjects").then((d) => d.subjects),
  });
}

export function useCreateSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api.post<{ subject: Subject }>("/api/subjects", { name }).then((d) => d.subject),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: subjectsKey }),
  });
}
```

- [ ] **Step 6: Write `frontend/src/pages/SubjectsPage.tsx`**

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import AppShell from "../components/AppShell";
import Button from "../components/Button";
import Field from "../components/Field";
import SubjectsTable from "../features/subjects/SubjectsTable";
import { useCreateSubject, useSubjects } from "../features/subjects/useSubjects";
import { ApiError } from "../lib/api";

export default function SubjectsPage() {
  const navigate = useNavigate();
  const { data: subjects, isLoading, isError, refetch } = useSubjects();
  const createSubject = useCreateSubject();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const subject = await createSubject.mutateAsync(name.trim());
      setName("");
      setAdding(false);
      navigate(`/subjects/${subject.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not create the subject.");
    }
  }

  return (
    <AppShell breadcrumb={<span className="now">Subjects</span>}>
      <div className="page-head">
        <div>
          <h1>Subjects</h1>
          <p>Each subject is a separate library. Questions only ever search the subject you're in.</p>
        </div>
        <Button size="sm" onClick={() => setAdding((open) => !open)}>
          {adding ? "Cancel" : "New subject"}
        </Button>
      </div>

      {adding ? (
        <form className="new-subject" onSubmit={onCreate}>
          <Field
            id="subject-name"
            label="Subject name"
            required
            autoFocus
            placeholder="e.g. Thermodynamics"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={createSubject.isPending || !name.trim()}>
            {createSubject.isPending ? "Creating…" : "Create"}
          </Button>
          {error ? <p className="auth-error">{error}</p> : null}
        </form>
      ) : null}

      {isLoading ? <p className="mono">Loading…</p> : null}

      {isError ? (
        <div className="tbl-blank">
          Could not load your subjects.{" "}
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : null}

      {subjects ? (
        <SubjectsTable subjects={subjects} onOpen={(id) => navigate(`/subjects/${id}`)} />
      ) : null}
    </AppShell>
  );
}
```

- [ ] **Step 7: Append the new-subject form styles to `frontend/src/styles/pages.css`**

```css
.new-subject {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px;
  margin-bottom: 18px;
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--wash);
}
.new-subject .field {
  flex: 1;
  min-width: 220px;
}
```

- [ ] **Step 8: Run the tests**

```bash
cd frontend && npx vitest run src/features/subjects/SubjectsTable.test.tsx
```
Expected: PASS (4 tests).

- [ ] **Step 9: Commit**

```bash
git add frontend/src
git commit -m "feat: add subjects page with summary table and inline create form"
```

---

### Task 12: Citation numbering

**Files:**
- Create: `frontend/src/lib/citations.ts`
- Test: `frontend/src/lib/citations.test.ts`

**Interfaces:**
- Produces: `numberCitations(citations: Citation[]) -> NumberedCitation[]` where `NumberedCitation = Citation & { n: number }`. Numbering is per message, deduplicated by `filename + source_label`, in first-appearance order.

- [ ] **Step 1: Write the failing test**

```ts
// src/lib/citations.test.ts
import { describe, expect, it } from "vitest";

import { numberCitations } from "./citations";

describe("numberCitations", () => {
  it("numbers citations from one in first-appearance order", () => {
    const result = numberCitations([
      { filename: "a.pdf", source_label: "page 1" },
      { filename: "b.pdf", source_label: "page 4" },
    ]);
    expect(result).toEqual([
      { filename: "a.pdf", source_label: "page 1", n: 1 },
      { filename: "b.pdf", source_label: "page 4", n: 2 },
    ]);
  });

  it("collapses duplicates of the same file and page", () => {
    const result = numberCitations([
      { filename: "a.pdf", source_label: "page 1" },
      { filename: "a.pdf", source_label: "page 1" },
      { filename: "a.pdf", source_label: "page 2" },
    ]);
    expect(result.map((c) => c.n)).toEqual([1, 2]);
    expect(result[1].source_label).toBe("page 2");
  });

  it("returns an empty list for an uncited answer", () => {
    expect(numberCitations([])).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/lib/citations.test.ts
```
Expected: FAIL — cannot resolve `./citations`.

- [ ] **Step 3: Write `frontend/src/lib/citations.ts`**

```ts
import type { Citation } from "./types";

export type NumberedCitation = Citation & { n: number };

/**
 * Number a single message's citations.
 *
 * Numbering is per message on purpose: a conversation-wide sequence would
 * renumber earlier answers whenever a new document was added.
 */
export function numberCitations(citations: Citation[]): NumberedCitation[] {
  const seen = new Set<string>();
  const numbered: NumberedCitation[] = [];

  for (const citation of citations) {
    const key = `${citation.filename}\u0000${citation.source_label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    numbered.push({ ...citation, n: numbered.length + 1 });
  }

  return numbered;
}
```

- [ ] **Step 4: Run the test**

```bash
cd frontend && npx vitest run src/lib/citations.test.ts
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib
git commit -m "feat: add per-message citation numbering"
```

---

### Task 13: Sources panel with upload, polling, and delete

**Files:**
- Create: `frontend/src/features/documents/useDocuments.ts`, `frontend/src/features/documents/SourcesPanel.tsx`
- Modify: `frontend/src/styles/pages.css` (append sources styles)
- Test: `frontend/src/features/documents/SourcesPanel.test.tsx`

**Interfaces:**
- Consumes: `api`, `Doc`, `Card`, `CardHead`, `StatusDot`.
- Produces: `useDocuments(subjectId)` — polls every 3s **only while** a document is `processing`; `useUploadDocument(subjectId)`, `useDeleteDocument(subjectId)`; `<SourcesPanel subjectId={string} />`.

- [ ] **Step 1: Append the sources styles to `frontend/src/styles/pages.css`**

```css
/* ---------- subject detail + sources ---------- */
.detail-top {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 22px;
}
.detail-top h1 {
  font-size: 20px;
  letter-spacing: -0.026em;
}
.split {
  display: grid;
  grid-template-columns: 316px 1fr;
  gap: 22px;
  align-items: start;
}

.drop {
  margin: 14px 14px 10px;
  padding: 20px 14px;
  border: 1px dashed var(--line-strong);
  border-radius: 7px;
  text-align: center;
  background: var(--wash);
  cursor: pointer;
  width: calc(100% - 28px);
  font-family: inherit;
  color: inherit;
}
.drop:hover,
.drop.dragging {
  border-color: var(--ink);
}
.drop .t {
  font-size: 13px;
  font-weight: 500;
}
.drop .s {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--ink-3);
  margin-top: 5px;
  text-transform: uppercase;
}

.srcs {
  list-style: none;
  margin: 0;
  padding: 4px 8px 10px;
  display: flex;
  flex-direction: column;
}
.src {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 7px;
  border-radius: var(--r-sm);
}
.src:hover {
  background: var(--wash);
}
.src-n {
  width: 19px;
  height: 19px;
  border-radius: 4px;
  border: 1px solid var(--line-strong);
  display: grid;
  place-items: center;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-2);
  flex-shrink: 0;
  font-weight: 500;
}
.src-b {
  min-width: 0;
  flex: 1;
}
.src-name {
  font-family: var(--mono);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
}
.src-meta {
  font-size: 11px;
  color: var(--ink-3);
  margin-top: 1px;
}
.src-x {
  background: none;
  border: none;
  color: var(--ink-3);
  cursor: pointer;
  font-size: 14px;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0;
}
.src:hover .src-x,
.src-x:focus-visible {
  opacity: 1;
}
.src-x:hover {
  color: var(--err);
  background: var(--wash-2);
}
.src-blank {
  padding: 4px 15px 16px;
  font-size: 12.5px;
  color: var(--ink-3);
}

@media (max-width: 940px) {
  .split {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 2: Write the failing test**

```tsx
// src/features/documents/SourcesPanel.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../../test/server";
import type { Doc } from "../../lib/types";
import SourcesPanel from "./SourcesPanel";

const READY: Doc = { id: "d1", filename: "ohms_law.pdf", status: "ready", error: null, created_at: null };
const FAILED: Doc = {
  id: "d2", filename: "bad.pdf", status: "failed",
  error: "No readable text found in file", created_at: null,
};

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SourcesPanel subjectId="s1" />
    </QueryClientProvider>,
  );
}

describe("SourcesPanel", () => {
  it("lists documents with their source numbers", async () => {
    server.use(
      http.get("/api/subjects/s1/documents", () =>
        HttpResponse.json({ documents: [READY, { ...READY, id: "d9", filename: "second.pdf" }] }),
      ),
    );
    renderPanel();
    await screen.findByText("ohms_law.pdf");

    // Scope to the list rows: the panel header also renders a count digit.
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("1");
    expect(rows[0]).toHaveTextContent("ohms_law.pdf");
    expect(rows[1]).toHaveTextContent("2");
    expect(rows[1]).toHaveTextContent("second.pdf");
  });

  it("shows the backend's reason on a failed document", async () => {
    server.use(
      http.get("/api/subjects/s1/documents", () => HttpResponse.json({ documents: [FAILED] })),
    );
    renderPanel();
    expect(await screen.findByText("No readable text found in file")).toBeInTheDocument();
  });

  it("prompts to add a source when there are none", async () => {
    server.use(http.get("/api/subjects/s1/documents", () => HttpResponse.json({ documents: [] })));
    renderPanel();
    expect(await screen.findByText(/no sources yet/i)).toBeInTheDocument();
  });

  it("removes a document when its delete button is used", async () => {
    let documents = [READY];
    server.use(
      http.get("/api/subjects/s1/documents", () => HttpResponse.json({ documents })),
      http.delete("/api/subjects/s1/documents/d1", () => {
        documents = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPanel();
    await screen.findByText("ohms_law.pdf");

    await userEvent.click(screen.getByRole("button", { name: /remove ohms_law.pdf/i }));

    await waitFor(() => expect(screen.queryByText("ohms_law.pdf")).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/features/documents/SourcesPanel.test.tsx
```
Expected: FAIL — cannot resolve `./SourcesPanel`.

- [ ] **Step 4: Write `frontend/src/features/documents/useDocuments.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { subjectsKey } from "../subjects/useSubjects";
import type { Doc } from "../../lib/types";

export const documentsKey = (subjectId: string) => ["documents", subjectId] as const;

export function useDocuments(subjectId: string) {
  return useQuery({
    queryKey: documentsKey(subjectId),
    queryFn: () =>
      api.get<{ documents: Doc[] }>(`/api/subjects/${subjectId}/documents`).then((d) => d.documents),
    // Poll only while something is still indexing, then stop.
    refetchInterval: (query) =>
      query.state.data?.some((doc) => doc.status === "processing") ? 3000 : false,
  });
}

export function useUploadDocument(subjectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      api
        .upload<{ document: Doc }>(`/api/subjects/${subjectId}/documents`, file)
        .then((d) => d.document),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentsKey(subjectId) });
      queryClient.invalidateQueries({ queryKey: subjectsKey });
    },
  });
}

export function useDeleteDocument(subjectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      api.del(`/api/subjects/${subjectId}/documents/${documentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentsKey(subjectId) });
      queryClient.invalidateQueries({ queryKey: subjectsKey });
    },
  });
}
```

- [ ] **Step 5: Write `frontend/src/features/documents/SourcesPanel.tsx`**

```tsx
import { useRef, useState } from "react";

import { Card, CardHead } from "../../components/Card";
import StatusDot from "../../components/StatusDot";
import { ApiError } from "../../lib/api";
import type { Doc } from "../../lib/types";
import { useDeleteDocument, useDocuments, useUploadDocument } from "./useDocuments";

function meta(doc: Doc): string {
  if (doc.status === "processing") return "Indexing…";
  if (doc.status === "failed") return doc.error ?? "Could not be processed";
  return "Indexed";
}

function tone(doc: Doc): "ok" | "wait" | "err" {
  if (doc.status === "ready") return "ok";
  if (doc.status === "failed") return "err";
  return "wait";
}

export default function SourcesPanel({ subjectId }: { subjectId: string }) {
  const { data: documents, isLoading } = useDocuments(subjectId);
  const upload = useUploadDocument(subjectId);
  const remove = useDeleteDocument(subjectId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  async function send(file: File | undefined) {
    if (!file) return;
    setError("");
    try {
      await upload.mutateAsync(file);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Upload failed. Try again.");
    }
  }

  return (
    <Card>
      <CardHead left="Sources" right={documents ? String(documents.length) : ""} />

      <button
        type="button"
        className={`drop ${dragging ? "dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void send(e.dataTransfer.files[0]);
        }}
      >
        <div className="t">{upload.isPending ? "Uploading…" : "Add a document"}</div>
        <div className="s">PDF · DOCX · PPTX · Photo</div>
      </button>

      <input
        ref={inputRef}
        type="file"
        hidden
        aria-label="Upload a document"
        accept=".pdf,.docx,.pptx,image/*"
        onChange={(e) => {
          void send(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {error ? <p className="src-blank" style={{ color: "var(--err)" }}>{error}</p> : null}

      {isLoading ? <p className="src-blank">Loading sources…</p> : null}

      {documents && documents.length === 0 ? (
        <p className="src-blank">No sources yet. Add one to start asking questions.</p>
      ) : null}

      {documents && documents.length > 0 ? (
        <ul className="srcs">
          {documents.map((doc, index) => (
            <li className="src" key={doc.id}>
              <span className="src-n">{index + 1}</span>
              <div className="src-b">
                <div className="src-name">{doc.filename}</div>
                <div className="src-meta">{meta(doc)}</div>
              </div>
              <StatusDot tone={tone(doc)} />
              <button
                className="src-x"
                aria-label={`Remove ${doc.filename}`}
                onClick={() => remove.mutate(doc.id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
```

- [ ] **Step 6: Run the tests**

```bash
cd frontend && npx vitest run src/features/documents/SourcesPanel.test.tsx
```
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: add sources panel with upload, status polling, and delete"
```

---

### Task 14: Chat panel and message rendering

**Files:**
- Create: `frontend/src/features/chat/useChat.ts`, `frontend/src/features/chat/ChatMessage.tsx`, `frontend/src/features/chat/ChatPanel.tsx`
- Modify: `frontend/src/styles/pages.css` (append chat styles)
- Test: `frontend/src/features/chat/ChatMessage.test.tsx`

**Interfaces:**
- Consumes: `api`, `Message`, `numberCitations`, `Card`, `CardHead`, `StatusDot`, `Button`.
- Produces: `useMessages(subjectId)`, `useAsk(subjectId)`, `useAskGeneral(subjectId)`; `<ChatMessage message={Message} onAskGeneral={(question: string) => void} pending={boolean} />`; `<ChatPanel subjectId={string} subjectName={string} hasReadyDocuments={boolean} />`.

- [ ] **Step 1: Append the chat styles to `frontend/src/styles/pages.css`**

```css
/* ---------- chat ---------- */
.chat {
  display: flex;
  flex-direction: column;
  height: 618px;
}
.thread {
  flex: 1;
  overflow-y: auto;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}
.thread-blank {
  margin: auto;
  text-align: center;
  color: var(--ink-3);
  font-size: 13.5px;
  max-width: 260px;
}

.ask {
  align-self: flex-end;
  max-width: 74%;
  background: var(--wash-2);
  border-radius: 12px 12px 3px 12px;
  padding: 10px 14px;
  font-size: 14px;
}

.reply {
  max-width: 88%;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.reply-body {
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--ink);
  white-space: pre-wrap;
}
.cite {
  display: inline-grid;
  place-items: center;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  border-radius: 3px;
  background: var(--wash-2);
  border: 1px solid var(--line-strong);
  font-family: var(--mono);
  font-size: 9.5px;
  color: var(--ink-2);
  vertical-align: 1px;
  margin-left: 3px;
}
.reply-srcs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 9px;
  border-top: 1px solid var(--line);
}
.src-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 5px;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-2);
  background: var(--paper);
}
.src-chip .i {
  color: var(--ink-3);
}

.miss {
  border-left: 2px solid var(--line-strong);
  padding-left: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
}
.miss .txt {
  font-size: 14px;
  color: var(--ink-2);
}
.general {
  border-left: 2px solid var(--wait);
  padding-left: 14px;
}

.composer {
  display: flex;
  gap: 9px;
  padding: 13px 16px;
  border-top: 1px solid var(--line);
}
.composer input {
  flex: 1;
  font: inherit;
  font-size: 14px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--line-strong);
  background: var(--paper);
  color: var(--ink);
}
.composer input:focus {
  outline: none;
  border-color: var(--ink);
  box-shadow: 0 0 0 3px var(--wash-2);
}
.composer input::placeholder {
  color: var(--ink-3);
}
.send {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: var(--ink);
  color: var(--paper);
  border: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  font-size: 14px;
  flex-shrink: 0;
}
.send:hover:not(:disabled) {
  background: var(--ink-2);
}
.send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

- [ ] **Step 2: Write the failing message test**

```tsx
// src/features/chat/ChatMessage.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Message } from "../../lib/types";
import ChatMessage from "./ChatMessage";

const GROUNDED: Message = {
  id: "m1",
  question: "What is Ohm's Law?",
  answer: "Voltage equals current times resistance.",
  citations: [
    { filename: "ohms_law.pdf", source_label: "page 1" },
    { filename: "ohms_law.pdf", source_label: "page 1" },
  ],
  response_mode: "rag",
  found: true,
  created_at: null,
};

const MISSING: Message = {
  id: "m2",
  question: "Capital of France?",
  answer: "Not found in your uploaded material.",
  citations: [],
  response_mode: "rag",
  found: false,
  created_at: null,
};

const GENERAL: Message = {
  id: "m3",
  question: "Capital of France?",
  answer: "Paris.",
  citations: [],
  response_mode: "general",
  found: true,
  created_at: null,
};

describe("ChatMessage", () => {
  it("renders a grounded answer with one deduplicated source chip", () => {
    render(<ChatMessage message={GROUNDED} onAskGeneral={vi.fn()} pending={false} />);
    expect(screen.getByText("What is Ohm's Law?")).toBeInTheDocument();
    expect(screen.getByText(/voltage equals current/i)).toBeInTheDocument();
    expect(screen.getByText("Grounded")).toBeInTheDocument();
    expect(screen.getAllByText(/ohms_law\.pdf/)).toHaveLength(1);
  });

  it("offers a general answer when nothing was found", async () => {
    const onAskGeneral = vi.fn();
    render(<ChatMessage message={MISSING} onAskGeneral={onAskGeneral} pending={false} />);

    expect(screen.getByText(/not in your material/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /answer from general knowledge/i }));

    expect(onAskGeneral).toHaveBeenCalledWith("Capital of France?");
  });

  it("labels a general answer as unsourced and offers no fallback button", () => {
    render(<ChatMessage message={GENERAL} onAskGeneral={vi.fn()} pending={false} />);
    expect(screen.getByText(/general ai · unsourced/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/features/chat/ChatMessage.test.tsx
```
Expected: FAIL — cannot resolve `./ChatMessage`.

- [ ] **Step 4: Write `frontend/src/features/chat/ChatMessage.tsx`**

```tsx
import Button from "../../components/Button";
import StatusDot from "../../components/StatusDot";
import { numberCitations } from "../../lib/citations";
import type { Message } from "../../lib/types";

type Props = {
  message: Message;
  onAskGeneral: (question: string) => void;
  pending: boolean;
};

export default function ChatMessage({ message, onAskGeneral, pending }: Props) {
  const cited = numberCitations(message.citations);
  const isGeneral = message.response_mode === "general";

  return (
    <>
      <div className="ask">{message.question}</div>

      {!message.found ? (
        <div className="reply">
          <div className="miss">
            <span className="mono">Not in your material</span>
            <div className="txt">Nothing in this subject's sources answers that.</div>
            <Button
              variant="outline"
              size="sm"
              disabled={pending}
              onClick={() => onAskGeneral(message.question)}
            >
              Answer from general knowledge
            </Button>
          </div>
        </div>
      ) : (
        <div className={`reply ${isGeneral ? "general" : ""}`}>
          {isGeneral ? (
            <StatusDot tone="wait" label="General AI · unsourced" />
          ) : (
            <StatusDot tone="ok" label="Grounded" />
          )}

          <div className="reply-body">
            {message.answer}
            {cited.map((citation) => (
              <span className="cite" key={citation.n}>
                {citation.n}
              </span>
            ))}
          </div>

          {cited.length > 0 ? (
            <div className="reply-srcs">
              {cited.map((citation) => (
                <span className="src-chip" key={citation.n}>
                  <span className="i">{citation.n}</span> {citation.filename} · {citation.source_label}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 5: Write `frontend/src/features/chat/useChat.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { subjectsKey } from "../subjects/useSubjects";
import type { Message } from "../../lib/types";

export const messagesKey = (subjectId: string) => ["messages", subjectId] as const;

export function useMessages(subjectId: string) {
  return useQuery({
    queryKey: messagesKey(subjectId),
    queryFn: () =>
      api.get<{ messages: Message[] }>(`/api/subjects/${subjectId}/messages`).then((d) => d.messages),
  });
}

function useAskMutation(subjectId: string, path: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (question: string) =>
      api.post<{ message: Message }>(path, { question }).then((d) => d.message),
    onSuccess: (message) => {
      queryClient.setQueryData<Message[]>(messagesKey(subjectId), (previous) => [
        ...(previous ?? []),
        message,
      ]);
      queryClient.invalidateQueries({ queryKey: subjectsKey });
    },
  });
}

export function useAsk(subjectId: string) {
  return useAskMutation(subjectId, `/api/subjects/${subjectId}/messages`);
}

export function useAskGeneral(subjectId: string) {
  return useAskMutation(subjectId, `/api/subjects/${subjectId}/messages/general`);
}
```

- [ ] **Step 6: Write `frontend/src/features/chat/ChatPanel.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Card, CardHead } from "../../components/Card";
import { ApiError } from "../../lib/api";
import ChatMessage from "./ChatMessage";
import { useAsk, useAskGeneral, useMessages } from "./useChat";

type Props = {
  subjectId: string;
  subjectName: string;
  hasReadyDocuments: boolean;
};

export default function ChatPanel({ subjectId, subjectName, hasReadyDocuments }: Props) {
  const { data: messages, isLoading } = useMessages(subjectId);
  const ask = useAsk(subjectId);
  const askGeneral = useAskGeneral(subjectId);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  const pending = ask.isPending || askGeneral.isPending;

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [messages?.length, pending]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text) return;
    setError("");
    setQuestion("");
    try {
      await ask.mutateAsync(text);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server. Try again.");
    }
  }

  async function askGenerally(text: string) {
    setError("");
    try {
      await askGeneral.mutateAsync(text);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server. Try again.");
    }
  }

  return (
    <Card className="chat">
      <CardHead left="Chat" right={`${subjectName} only`} />

      <div className="thread" ref={threadRef}>
        {isLoading ? <p className="mono">Loading…</p> : null}

        {messages && messages.length === 0 && !pending ? (
          <p className="thread-blank">
            {hasReadyDocuments
              ? "Ask anything — answers come only from this subject's sources."
              : "Add a source and wait for it to finish indexing, then ask your first question."}
          </p>
        ) : null}

        {messages?.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
            onAskGeneral={askGenerally}
            pending={pending}
          />
        ))}

        {pending ? <p className="mono">Thinking…</p> : null}
        {error ? <p className="auth-error">{error}</p> : null}
      </div>

      <form className="composer" onSubmit={submit}>
        <input
          type="text"
          aria-label="Ask a question"
          placeholder={
            hasReadyDocuments
              ? `Ask anything from your ${subjectName} sources…`
              : "Waiting for a source to finish indexing…"
          }
          value={question}
          disabled={pending || !hasReadyDocuments}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="send" type="submit" aria-label="Send" disabled={pending || !question.trim()}>
          ↑
        </button>
      </form>
    </Card>
  );
}
```

- [ ] **Step 7: Run the tests**

```bash
cd frontend && npx vitest run src/features/chat/ChatMessage.test.tsx
```
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: add chat panel with grounded, not-found, and general answer states"
```

---

### Task 15: Subject detail page

**Files:**
- Create: `frontend/src/pages/SubjectDetailPage.tsx`

**Interfaces:**
- Consumes: `useSubjects` (to find the subject name), `useDocuments`, `SourcesPanel`, `ChatPanel`, `AppShell`, `api`.
- Produces: `SubjectDetailPage` — reads `subjectId` from the route, renders the split view.

- [ ] **Step 1: Write `frontend/src/pages/SubjectDetailPage.tsx`**

```tsx
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import AppShell from "../components/AppShell";
import ChatPanel from "../features/chat/ChatPanel";
import SourcesPanel from "../features/documents/SourcesPanel";
import { useDocuments } from "../features/documents/useDocuments";
import { api } from "../lib/api";
import type { Subject } from "../lib/types";

export default function SubjectDetailPage() {
  const { subjectId = "" } = useParams();

  const subjectQuery = useQuery({
    queryKey: ["subject", subjectId],
    queryFn: () =>
      api.get<{ subject: Subject }>(`/api/subjects/${subjectId}`).then((d) => d.subject),
  });

  const { data: documents } = useDocuments(subjectId);
  const readyCount = documents?.filter((doc) => doc.status === "ready").length ?? 0;

  if (subjectQuery.isError) {
    return (
      <AppShell breadcrumb={<span className="now">Not found</span>}>
        <div className="tbl-blank">
          That subject does not exist. <Link to="/subjects">Back to subjects</Link>
        </div>
      </AppShell>
    );
  }

  const name = subjectQuery.data?.name ?? "";

  return (
    <AppShell
      breadcrumb={
        <>
          <Link to="/subjects">Subjects</Link>
          <span>/</span>
          <span className="now">{name}</span>
        </>
      }
      sidebarExtra={
        <>
          <div className="mono">This subject</div>
          <span className="side-link">
            <span className="sq" /> {documents?.length ?? 0} documents
          </span>
        </>
      }
    >
      <div className="detail-top">
        <h1>{name}</h1>
        <span className="mono">
          {readyCount} of {documents?.length ?? 0} sources indexed
        </span>
      </div>

      <div className="split">
        <SourcesPanel subjectId={subjectId} />
        <ChatPanel subjectId={subjectId} subjectName={name} hasReadyDocuments={readyCount > 0} />
      </div>
    </AppShell>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SubjectDetailPage.tsx
git commit -m "feat: add subject detail page combining sources and chat"
```

---

### Task 16: Routing and 401-driven session expiry

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: every page and provider built so far.
- Produces: the wired application — `/login`, `/signup` public; `/subjects`, `/subjects/:subjectId` protected; unknown paths redirect to `/subjects`. A `401` from any query or mutation clears the session and sends the user to `/login`.

- [ ] **Step 1: Write the failing test**

```tsx
// src/App.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import App from "./App";
import { server } from "./test/server";

describe("App routing", () => {
  it("sends an unauthenticated visitor to the login screen", async () => {
    server.use(
      http.get("/api/auth/me", () =>
        HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
      ),
    );

    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument(),
    );
  });

  it("shows the subjects screen to an authenticated visitor", async () => {
    server.use(
      http.get("/api/auth/me", () => HttpResponse.json({ user: { id: "u1", email: "s@e.com" } })),
      http.get("/api/subjects", () => HttpResponse.json({ subjects: [] })),
    );

    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Subjects" })).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/App.test.tsx
```
Expected: FAIL — the placeholder `App` renders only a heading.

- [ ] **Step 3: Write `frontend/src/App.tsx`**

```tsx
import { QueryCache, QueryClient, QueryClientProvider, MutationCache } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./auth/ProtectedRoute";
import { AuthProvider } from "./auth/AuthContext";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import SubjectDetailPage from "./pages/SubjectDetailPage";
import SubjectsPage from "./pages/SubjectsPage";
import { ApiError } from "./lib/api";

// A 401 from any request means the session ended. Send the user to /login
// once, from a single place, rather than handling it in every component.
function onUnauthorized(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        error instanceof ApiError && error.status >= 400 && error.status < 500
          ? false
          : failureCount < 2,
      refetchOnWindowFocus: false,
    },
  },
  queryCache: new QueryCache({ onError: onUnauthorized }),
  mutationCache: new MutationCache({ onError: onUnauthorized }),
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/subjects" element={<SubjectsPage />} />
              <Route path="/subjects/:subjectId" element={<SubjectDetailPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/subjects" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 4: Run the whole frontend suite**

```bash
cd frontend && npx vitest run
```
Expected: PASS — all frontend tests across every task.

- [ ] **Step 5: Add a `test` script to `frontend/package.json`**

In `"scripts"`, add:

```json
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
```

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: wire routing, protected routes, and global 401 session expiry"
```

---

### Task 17: Serve the SPA from FastAPI and retire the Jinja frontend

**Files:**
- Modify: `app/main.py`
- Delete: `app/templates.py`, `app/templates/` (whole directory)
- Modify: `app/auth.py`, `app/subjects.py`, `app/chat.py`, `app/documents.py` (remove HTML routes)
- Delete: `tests/test_navigation.py`, `tests/test_subject_detail.py`
- Modify: `tests/test_auth.py`, `tests/test_subjects.py`, `tests/test_chat.py`, `tests/test_documents.py` (drop HTML-route tests, keep domain tests)
- Test: `tests/test_spa_serving.py`

**Interfaces:**
- Produces: FastAPI serving `frontend/dist` at `/`, with `/api/*` and `/health` unaffected; the Jinja2 frontend removed so there is exactly one frontend.

- [ ] **Step 1: Build the frontend**

```bash
cd frontend && npm run build
```
Expected: `frontend/dist/index.html` and `frontend/dist/assets/` exist.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_spa_serving.py
import pytest

from app.main import FRONTEND_DIST

pytestmark = pytest.mark.skipif(
    not (FRONTEND_DIST / "index.html").is_file(),
    reason="frontend not built; run `npm run build` in frontend/",
)


def test_root_serves_the_spa_shell(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<div id=\"root\">" in response.text


def test_client_route_serves_the_spa_shell(client):
    response = client.get("/subjects/some-id")
    assert response.status_code == 200
    assert "<div id=\"root\">" in response.text


def test_api_paths_are_not_swallowed_by_the_spa_catch_all(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


def test_health_still_returns_json(client):
    assert client.get("/health").json() == {"status": "ok"}
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_spa_serving.py -v`
Expected: FAIL — `cannot import name 'FRONTEND_DIST'`.

- [ ] **Step 4: Remove the HTML routes from the domain modules**

In each file, delete the route functions and the now-unused imports, keeping every domain function and its tests intact.

- `app/auth.py` — delete `signup_form`, `signup`, `login_form`, `login`, `logout`, the `router` object, and the `APIRouter`, `Form`, `RedirectResponse`, `templates` imports. Keep `hash_password`, `verify_password`, `create_user`, `authenticate_user`, `get_current_user`.
- `app/subjects.py` — delete `subjects_page`, `create_subject_route`, `rename_subject_route`, `delete_subject_route`, `subject_detail_page`, the `router`, and the `APIRouter`, `Form`, `Request`, `RedirectResponse`, `HTTPException`, `templates`, `get_current_user`, and `list_chat_history` imports. Keep `create_subject`, `list_subjects`, `get_subject`, `rename_subject`, `delete_subject`, and `list_subject_summaries` — and keep the `list_documents`, `chats_collection`, and `serialize_subject` imports, which `list_subject_summaries` still needs.
- `app/chat.py` — delete `ask_question`, `ask_general`, the `router`, and the `APIRouter`, `Form`, `Request`, `templates`, `answer_general`, `answer_question` imports. Keep `save_chat_message` and `list_chat_history`.
- `app/documents.py` — delete `upload_document`, `documents_list_partial`, the `router`, and the `APIRouter`, `BackgroundTasks`, `File`, `Request`, `templates` imports. Keep `UploadFile` (used by `save_upload`) and every domain function.

- [ ] **Step 5: Delete the template layer**

```bash
git rm app/templates.py
git rm -r app/templates
```

- [ ] **Step 6: Rewrite `app/main.py`**

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as api_auth_router
from app.api.chat import router as api_chat_router
from app.api.documents import router as api_documents_router
from app.api.subjects import router as api_subjects_router
from app.config import settings

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Exam Partner")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="kb_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.session_https_only,
)

app.include_router(api_auth_router)
app.include_router(api_subjects_router)
app.include_router(api_documents_router)
app.include_router(api_chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the built SPA. Registered last so /api/* and /health always win, and
# every other path returns index.html so client-side routing survives refresh.
if (FRONTEND_DIST / "index.html").is_file():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
```

The redirecting 401 handler is gone: there are no HTML pages left to redirect to, and `/api/*` already returns JSON `401`s that the SPA handles.

- [ ] **Step 7: Remove the tests for the deleted HTML routes**

```bash
git rm tests/test_navigation.py tests/test_subject_detail.py
```

Then edit the remaining test files:

- `tests/test_auth.py` — delete `test_signup_then_access_protected_page` and `test_login_with_wrong_password_shows_error`. Keep the five domain tests.
- `tests/test_subjects.py` — delete `test_subjects_page_requires_login` and `test_create_subject_via_form`. Keep the four domain tests.
- `tests/test_chat.py` — delete `test_ask_question_endpoint_saves_rag_response` and `test_ask_general_endpoint_saves_general_response` (covered by `tests/test_api_chat.py`). Keep the three domain tests.
- `tests/test_documents.py` — no changes; it tests only domain functions.
- `tests/conftest.py` — replace the `authed_client` fixture body with the JSON API, since the HTML `/login` route is gone:

```python
@pytest.fixture
def authed_client(client, db):
    from app.auth import create_user

    user = create_user(db, "student@example.com", "password123")
    client.post("/api/auth/login", json={"email": "student@example.com", "password": "password123"})
    return client, user
```

- [ ] **Step 8: Run the full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS. Every remaining test covers either a domain function or a JSON endpoint.

- [ ] **Step 9: Run the frontend suite and typecheck**

```bash
cd frontend && npm run test && npm run typecheck
```
Expected: PASS, no type errors.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: serve the React SPA from FastAPI and remove the Jinja frontend"
```

---

### Task 18: Manual end-to-end verification

**Files:** None — manual QA against the real backend with real credentials.

- [ ] **Step 1: Confirm `.env` still holds real credentials**

`MONGODB_URI` must point at the Atlas cluster that has the `vector_index`, and `GEMINI_API_KEY` must be a working key.

- [ ] **Step 2: Start the backend**

```bash
cd "C:/Users/Unnati Bhawsar/Desktop/project1-exam_partner"
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 3: Start the frontend dev server in a second terminal**

```bash
cd "C:/Users/Unnati Bhawsar/Desktop/project1-exam_partner/frontend"
npm run dev
```
Visit `http://localhost:5173`.

- [ ] **Step 4: Sign up and confirm the redirect**

Create an account. Expected: you land on Subjects with an empty-state table and your initials in the top-right avatar.

- [ ] **Step 5: Confirm the session survives a refresh**

Press F5. Expected: you stay on Subjects — no flash of the login screen, no bounce to `/login`.

- [ ] **Step 6: Create a subject and open it**

Expected: the row appears with `0` documents, `—` last asked, and a "No sources" status; clicking it opens the split view.

- [ ] **Step 7: Upload a PDF**

Expected: the source appears immediately as "Indexing…" with an amber dot, and flips to "Indexed" with a green dot within a few seconds without a manual refresh. Confirm in the browser's Network tab that polling **stops** once it is ready.

- [ ] **Step 8: Upload a photo of handwritten notes**

Expected: same lifecycle; Gemini vision transcribes it and the status reaches "Indexed".

- [ ] **Step 9: Ask a grounded question**

Expected: an answer marked "Grounded" with numbered citation chips, and a source chip naming the correct file and page.

- [ ] **Step 10: Ask something the material does not cover**

Expected: the "Not in your material" block with the outline button. Click it. Expected: a second answer labelled "General AI · unsourced" with no citation chips.

- [ ] **Step 11: Reload the subject page**

Expected: the full conversation restores from history with each message keeping its correct state — grounded, not-found, and general all render as they did before the reload.

- [ ] **Step 12: Delete a source**

Expected: the row disappears and the count drops. Ask a question that only that document could answer. Expected: "Not in your material" — proving its chunks were removed from the vector store too.

- [ ] **Step 13: Verify user isolation**

Log out, sign up as a second user, create a subject with the same name, and ask the first user's grounded question. Expected: "Not in your material", with no citations from the first user's files.

- [ ] **Step 14: Verify the production build**

Stop the Vite dev server, then:

```bash
cd frontend && npm run build
```

With only uvicorn running, visit `http://localhost:8000`. Expected: the SPA loads from FastAPI, and refreshing on `/subjects/<some-id>` still works rather than 404ing.

- [ ] **Step 15: Record the outcome**

Do not mark this task complete until every step above passes against the real Atlas and Gemini backend. File any failure as a follow-up fix.
