# Exam Partner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a web app where a student uploads study material (PDFs, Word, PowerPoint, handwritten note photos) per subject, and asks questions that are answered strictly from that material, with citations, falling back to general AI only on explicit request.

**Architecture:** FastAPI backend (sync routes, Jinja2 + HTMX frontend, no JS build step) with MongoDB Atlas as the single datastore (documents + chat + Atlas Vector Search for embeddings), Gemini as the only AI backend (chat, embeddings, and vision transcription of handwritten notes), orchestrated with LangChain (`langchain-google-genai`, `langchain-mongodb`, `langchain-text-splitters`).

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pymongo (sync), mongomock (tests), passlib[bcrypt], itsdangerous (sessions), PyMuPDF, python-docx, python-pptx, langchain / langchain-google-genai / langchain-mongodb / langchain-text-splitters, Jinja2, htmx, pytest, httpx.

## Global Constraints

- Every retrieval query MUST filter by both `user_id` and `subject_id` — no cross-user or cross-subject leakage (spec: Chat flow step 2).
- Every stored chunk MUST have a unique `chunk_id` (spec: Upload flow step 5).
- Every chat message MUST record `response_mode` (`"rag"` or `"general"`) (spec: Chat flow step 7).
- Every RAG-grounded answer MUST include citations (filename + section/page); general-mode answers MUST NOT include citations (spec: Answering behavior).
- Document uploads are processed as a background task with status `processing` → `ready`/`failed`, never blocking the upload request (spec: Components).
- MongoDB Atlas is the only datastore (no SQLite, no separate local vector DB); Gemini is the only AI backend (spec: Architecture).
- Gemini calls and MongoDB Atlas calls MUST retry with backoff before surfacing a failure (spec: Error handling).
- App runs locally only in this phase — no deployment/hosting tasks.
- All collection-accessing functions take `db` as an explicit parameter (never a module-global connection) so tests can inject `mongomock`.

---

### Task 1: Project scaffolding & config

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Produces: `app.config.settings` (a `Settings` instance with `.mongodb_uri`, `.mongodb_db_name`, `.gemini_api_key`, `.session_secret`); `app.main.app` (the FastAPI instance).

- [x] **Step 1: Create `requirements.txt`**

```
fastapi
uvicorn[standard]
pydantic-settings
pymongo
passlib[bcrypt]
itsdangerous
python-multipart
PyMuPDF
python-docx
python-pptx
langchain
langchain-core
langchain-text-splitters
langchain-google-genai
langchain-mongodb
jinja2
mongomock
pytest
httpx
```

- [x] **Step 2: Create `.env.example`**

```
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=exam_partner
GEMINI_API_KEY=your-gemini-api-key
SESSION_SECRET=change-me-to-a-random-string
```

- [x] **Step 3: Set up the environment and install dependencies**

Run: `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt` (Windows) — confirm no install errors.

- [x] **Step 4: Create `app/__init__.py`** (empty file, makes `app` a package)

- [x] **Step 5: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mongodb_uri: str
    mongodb_db_name: str = "exam_partner"
    gemini_api_key: str
    session_secret: str


settings = Settings()
```

- [x] **Step 6: Write the failing test for the app**

```python
# tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [x] **Step 7: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_health.py -v`
Expected: FAIL (`app.main` doesn't exist yet). Before this, create a `.env` file (copy `.env.example`, fill in placeholder values — real credentials aren't needed yet since nothing calls Mongo/Gemini in this task).

- [x] **Step 8: Write `app/main.py`**

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings

app = FastAPI(title="Exam Partner")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [x] **Step 9: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_health.py -v`
Expected: PASS

- [x] **Step 10: Commit**

```bash
git add requirements.txt .env.example app/__init__.py app/config.py app/main.py tests/test_health.py
git commit -m "feat: scaffold FastAPI app with config and health check"
```

---

### Task 2: MongoDB connection, collection helpers, and test fixtures

**Files:**
- Create: `app/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `app.config.settings.mongodb_uri`, `.mongodb_db_name`.
- Produces: `get_db() -> Database` (FastAPI-dependency-compatible), `users_collection(db)`, `subjects_collection(db)`, `documents_collection(db)`, `chunks_collection(db)`, `chats_collection(db)` — each `(db) -> Collection`. Pytest fixtures `db` (mongomock database) and `client` (TestClient with `get_db` overridden) available to all tests via `conftest.py`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_db.py
import mongomock

from app.db import users_collection


def test_users_collection_is_named_users():
    db = mongomock.MongoClient()["test_db"]
    collection = users_collection(db)
    assert collection.name == "users"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `app.db`.

- [x] **Step 3: Write `app/db.py`**

```python
from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.config import settings


@lru_cache
def get_client() -> MongoClient:
    return MongoClient(settings.mongodb_uri)


def get_db() -> Database:
    return get_client()[settings.mongodb_db_name]


def users_collection(db: Database) -> Collection:
    return db["users"]


def subjects_collection(db: Database) -> Collection:
    return db["subjects"]


def documents_collection(db: Database) -> Collection:
    return db["documents"]


def chunks_collection(db: Database) -> Collection:
    return db["chunks"]


def chats_collection(db: Database) -> Collection:
    return db["chats"]
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_db.py -v`
Expected: PASS

- [x] **Step 5: Write `tests/conftest.py` (shared fixtures for all future tests)**

```python
import mongomock
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


@pytest.fixture
def db():
    return mongomock.MongoClient()["test_db"]


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [x] **Step 6: Run the full test suite to confirm fixtures don't break anything**

Run: `.venv/Scripts/pytest -v`
Expected: PASS (2 passed: `test_health`, `test_db`)

- [x] **Step 7: Commit**

```bash
git add app/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: add MongoDB connection helpers and shared test fixtures"
```

---

### Task 3: Auth (signup, login, logout, session)

**Files:**
- Create: `app/templates.py`
- Create: `app/templates/base.html`
- Create: `app/templates/signup.html`
- Create: `app/templates/login.html`
- Create: `app/auth.py`
- Modify: `app/main.py` (include auth router)
- Modify: `tests/conftest.py` (add `authed_client` fixture)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.db.users_collection`.
- Produces: `hash_password(password) -> str`, `verify_password(password, password_hash) -> bool`, `create_user(db, email, password) -> dict` (raises `ValueError` if email taken), `authenticate_user(db, email, password) -> dict | None`, `get_current_user(request, db) -> dict` (FastAPI dependency, raises `HTTPException(401)`), `router` (APIRouter with `/signup`, `/login`, `/logout`). User dict shape: `{"_id": str, "email": str, "password_hash": str, "created_at": datetime}`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
import pytest

from app.auth import authenticate_user, create_user, hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct-horse")
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_user_stores_hashed_password(db):
    user = create_user(db, "student@example.com", "password123")
    assert user["email"] == "student@example.com"
    assert user["password_hash"] != "password123"


def test_create_user_rejects_duplicate_email(db):
    create_user(db, "student@example.com", "password123")
    with pytest.raises(ValueError):
        create_user(db, "student@example.com", "another-password")


def test_authenticate_user_succeeds_with_correct_password(db):
    create_user(db, "student@example.com", "password123")
    user = authenticate_user(db, "student@example.com", "password123")
    assert user is not None
    assert user["email"] == "student@example.com"


def test_authenticate_user_fails_with_wrong_password(db):
    create_user(db, "student@example.com", "password123")
    assert authenticate_user(db, "student@example.com", "wrong") is None


def test_signup_then_access_protected_page(client):
    response = client.post(
        "/signup", data={"email": "student@example.com", "password": "password123"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_login_with_wrong_password_shows_error(client):
    client.post("/signup", data={"email": "student@example.com", "password": "password123"})
    client.cookies.clear()
    response = client.post("/login", data={"email": "student@example.com", "password": "wrong"})
    assert response.status_code == 400
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_auth.py -v`
Expected: FAIL (`app.auth` doesn't exist).

- [x] **Step 3: Write `app/templates.py`**

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
```

- [x] **Step 4: Write `app/templates/base.html`**

```html
<!DOCTYPE html>
<html>
<head>
  <title>Exam Partner</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body>
  <nav>
    <a href="/subjects">Subjects</a>
    {% if request.session.get("user_id") %}
    <form action="/logout" method="post" style="display:inline"><button type="submit">Log out</button></form>
    {% endif %}
  </nav>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [x] **Step 5: Write `app/templates/signup.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Sign up</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/signup">
  <input type="email" name="email" placeholder="Email" required>
  <input type="password" name="password" placeholder="Password" required minlength="8">
  <button type="submit">Sign up</button>
</form>
<p>Already have an account? <a href="/login">Log in</a></p>
{% endblock %}
```

- [x] **Step 6: Write `app/templates/login.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Log in</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/login">
  <input type="email" name="email" placeholder="Email" required>
  <input type="password" name="password" placeholder="Password" required>
  <button type="submit">Log in</button>
</form>
<p>No account? <a href="/signup">Sign up</a></p>
{% endblock %}
```

- [x] **Step 7: Write `app/auth.py`**

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from pymongo.database import Database

from app.db import get_db, users_collection
from app.templates import templates

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_user(db: Database, email: str, password: str) -> dict:
    if users_collection(db).find_one({"email": email}):
        raise ValueError("That email is already registered")
    user = {
        "_id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc),
    }
    users_collection(db).insert_one(user)
    return user


def authenticate_user(db: Database, email: str, password: str) -> dict | None:
    user = users_collection(db).find_one({"email": email})
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user


def get_current_user(request: Request, db: Database = Depends(get_db)) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = users_collection(db).find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/signup")
def signup_form(request: Request):
    return templates.TemplateResponse(request, "signup.html", {"error": None})


@router.post("/signup")
def signup(request: Request, email: str = Form(...), password: str = Form(...), db: Database = Depends(get_db)):
    try:
        user = create_user(db, email, password)
    except ValueError as exc:
        return templates.TemplateResponse(request, "signup.html", {"error": str(exc)}, status_code=400)
    request.session["user_id"] = user["_id"]
    return RedirectResponse(url="/subjects", status_code=303)


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Database = Depends(get_db)):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password"}, status_code=400
        )
    request.session["user_id"] = user["_id"]
    return RedirectResponse(url="/subjects", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
```

- [x] **Step 8: Modify `app/main.py` to include the auth router**

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.config import settings

app = FastAPI(title="Exam Partner")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [x] **Step 9: Add a placeholder `/subjects` route so the signup redirect doesn't 404 the test**

Add to `app/main.py` (temporary — Task 4 replaces this with the real route):

```python
@app.get("/subjects")
def subjects_placeholder():
    return {"status": "subjects page not built yet"}
```

- [x] **Step 10: Add `authed_client` fixture to `tests/conftest.py`**

```python
@pytest.fixture
def authed_client(client, db):
    from app.auth import create_user

    user = create_user(db, "student@example.com", "password123")
    client.post("/login", data={"email": "student@example.com", "password": "password123"})
    return client, user
```

- [x] **Step 11: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_auth.py -v`
Expected: PASS (all 7 tests)

- [x] **Step 12: Commit**

```bash
git add app/templates.py app/templates/base.html app/templates/signup.html app/templates/login.html app/auth.py app/main.py tests/conftest.py tests/test_auth.py
git commit -m "feat: add signup/login/logout with session auth"
```

---

### Task 4: Subject management (create, list, rename, delete)

**Files:**
- Create: `app/subjects.py`
- Create: `app/templates/subjects.html`
- Modify: `app/main.py` (include subjects router, remove placeholder `/subjects` route)
- Test: `tests/test_subjects.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.db.subjects_collection`, `app.auth.get_current_user`.
- Produces: `create_subject(db, user_id, name) -> dict`, `list_subjects(db, user_id) -> list[dict]`, `rename_subject(db, user_id, subject_id, new_name) -> None`, `delete_subject(db, user_id, subject_id) -> None`, `get_subject(db, user_id, subject_id) -> dict | None`, `router`. Subject dict shape: `{"_id": str, "user_id": str, "name": str, "created_at": datetime}`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_subjects.py
from app.subjects import create_subject, delete_subject, get_subject, list_subjects, rename_subject


def test_create_and_list_subjects(db):
    create_subject(db, "user-1", "Thermodynamics")
    create_subject(db, "user-1", "Data Structures")
    subjects = list_subjects(db, "user-1")
    assert [s["name"] for s in subjects] == ["Data Structures", "Thermodynamics"]


def test_list_subjects_only_returns_own_subjects(db):
    create_subject(db, "user-1", "Thermodynamics")
    create_subject(db, "user-2", "Other User's Subject")
    subjects = list_subjects(db, "user-1")
    assert len(subjects) == 1
    assert subjects[0]["name"] == "Thermodynamics"


def test_rename_subject(db):
    subject = create_subject(db, "user-1", "Thermo")
    rename_subject(db, "user-1", subject["_id"], "Thermodynamics")
    updated = get_subject(db, "user-1", subject["_id"])
    assert updated["name"] == "Thermodynamics"


def test_delete_subject(db):
    subject = create_subject(db, "user-1", "Thermodynamics")
    delete_subject(db, "user-1", subject["_id"])
    assert get_subject(db, "user-1", subject["_id"]) is None


def test_subjects_page_requires_login(client):
    response = client.get("/subjects", follow_redirects=False)
    assert response.status_code == 401


def test_create_subject_via_form(authed_client):
    client, user = authed_client
    response = client.post("/subjects", data={"name": "Thermodynamics"}, follow_redirects=False)
    assert response.status_code == 303
    response = client.get("/subjects")
    assert "Thermodynamics" in response.text
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_subjects.py -v`
Expected: FAIL (`app.subjects` doesn't exist).

- [x] **Step 3: Write `app/subjects.py`**

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.auth import get_current_user
from app.db import get_db, subjects_collection
from app.templates import templates

router = APIRouter()


def create_subject(db: Database, user_id: str, name: str) -> dict:
    subject = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": name,
        "created_at": datetime.now(timezone.utc),
    }
    subjects_collection(db).insert_one(subject)
    return subject


def list_subjects(db: Database, user_id: str) -> list[dict]:
    return list(subjects_collection(db).find({"user_id": user_id}).sort("name", 1))


def get_subject(db: Database, user_id: str, subject_id: str) -> dict | None:
    return subjects_collection(db).find_one({"_id": subject_id, "user_id": user_id})


def rename_subject(db: Database, user_id: str, subject_id: str, new_name: str) -> None:
    subjects_collection(db).update_one({"_id": subject_id, "user_id": user_id}, {"$set": {"name": new_name}})


def delete_subject(db: Database, user_id: str, subject_id: str) -> None:
    subjects_collection(db).delete_one({"_id": subject_id, "user_id": user_id})


@router.get("/subjects")
def subjects_page(request: Request, db: Database = Depends(get_db), user: dict = Depends(get_current_user)):
    subjects = list_subjects(db, user["_id"])
    return templates.TemplateResponse(request, "subjects.html", {"subjects": subjects})


@router.post("/subjects")
def create_subject_route(
    name: str = Form(...), db: Database = Depends(get_db), user: dict = Depends(get_current_user)
):
    create_subject(db, user["_id"], name)
    return RedirectResponse(url="/subjects", status_code=303)


@router.post("/subjects/{subject_id}/rename")
def rename_subject_route(
    subject_id: str,
    name: str = Form(...),
    db: Database = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    rename_subject(db, user["_id"], subject_id, name)
    return RedirectResponse(url="/subjects", status_code=303)


@router.post("/subjects/{subject_id}/delete")
def delete_subject_route(
    subject_id: str, db: Database = Depends(get_db), user: dict = Depends(get_current_user)
):
    delete_subject(db, user["_id"], subject_id)
    return RedirectResponse(url="/subjects", status_code=303)
```

- [x] **Step 4: Write `app/templates/subjects.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Your subjects</h1>
<form method="post" action="/subjects">
  <input type="text" name="name" placeholder="New subject name" required>
  <button type="submit">Create</button>
</form>
<ul>
  {% for subject in subjects %}
  <li>
    <a href="/subjects/{{ subject._id }}">{{ subject.name }}</a>
    <form method="post" action="/subjects/{{ subject._id }}/delete" style="display:inline">
      <button type="submit">Delete</button>
    </form>
  </li>
  {% endfor %}
</ul>
{% endblock %}
```

- [x] **Step 5: Modify `app/main.py`** — remove the placeholder `/subjects` route from Task 3 Step 9, include the subjects router instead

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.subjects import router as subjects_router

app = FastAPI(title="Exam Partner")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.include_router(auth_router)
app.include_router(subjects_router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [x] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/pytest -v`
Expected: PASS (all tests, including Tasks 1-3's)

- [x] **Step 7: Commit**

```bash
git add app/subjects.py app/templates/subjects.html app/main.py tests/test_subjects.py
git commit -m "feat: add subject create/list/rename/delete"
```

---

### Task 5: Text extraction (PDF, DOCX, PPTX)

**Files:**
- Create: `app/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Produces: `extract_pdf_pages(path: str) -> list[tuple[str, str]]`, `extract_docx_sections(path: str) -> list[tuple[str, str]]`, `extract_pptx_slides(path: str) -> list[tuple[str, str]]`. Each returns a list of `(source_label, text)` pairs, e.g. `("page 3", "...")`, skipping pages/slides with no text. These are consumed by Task 7's `extract_text` dispatcher and Task 8's chunker.

- [x] **Step 1: Write the failing tests (each generates its own tiny sample file, no fixtures needed)**

```python
# tests/test_extraction.py
import fitz
from docx import Document as DocxDocument
from pptx import Presentation

from app.extraction import extract_docx_sections, extract_pdf_pages, extract_pptx_slides


def test_extract_pdf_pages(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Newton's First Law of Motion")
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_pdf_pages(str(pdf_path))

    assert len(pages) == 1
    assert pages[0][0] == "page 1"
    assert "Newton" in pages[0][1]


def test_extract_pdf_skips_blank_pages(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    doc.new_page()  # blank
    page = doc.new_page()
    page.insert_text((72, 72), "Chapter 2: Thermodynamics")
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_pdf_pages(str(pdf_path))

    assert len(pages) == 1
    assert pages[0][0] == "page 2"


def test_extract_docx_sections(tmp_path):
    docx_path = tmp_path / "sample.docx"
    doc = DocxDocument()
    doc.add_paragraph("The mitochondria is the powerhouse of the cell.")
    doc.save(str(docx_path))

    sections = extract_docx_sections(str(docx_path))

    assert len(sections) == 1
    assert sections[0][0] == "document"
    assert "mitochondria" in sections[0][1]


def test_extract_pptx_slides(tmp_path):
    pptx_path = tmp_path / "sample.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Photosynthesis"
    prs.save(str(pptx_path))

    slides = extract_pptx_slides(str(pptx_path))

    assert len(slides) == 1
    assert slides[0][0] == "slide 1"
    assert "Photosynthesis" in slides[0][1]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_extraction.py -v`
Expected: FAIL (`app.extraction` doesn't exist).

- [x] **Step 3: Write `app/extraction.py`**

```python
import fitz
from docx import Document as DocxDocument
from pptx import Presentation


def extract_pdf_pages(path: str) -> list[tuple[str, str]]:
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if text:
            pages.append((f"page {i}", text))
    doc.close()
    return pages


def extract_docx_sections(path: str) -> list[tuple[str, str]]:
    doc = DocxDocument(path)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [("document", text)] if text else []


def extract_pptx_slides(path: str) -> list[tuple[str, str]]:
    prs = Presentation(path)
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        texts = [shape.text for shape in slide.shapes if shape.has_text_frame and shape.text.strip()]
        if texts:
            slides.append((f"slide {i}", "\n".join(texts)))
    return slides
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_extraction.py -v`
Expected: PASS (4 passed)

- [x] **Step 5: Commit**

```bash
git add app/extraction.py tests/test_extraction.py
git commit -m "feat: extract text from PDF, DOCX, and PPTX files"
```

---

### Task 6: Retry helper for external service calls

**Files:**
- Create: `app/retry.py`
- Test: `tests/test_retry.py`

**Interfaces:**
- Produces: `with_retries(fn: Callable[[], T], max_attempts: int = 3, base_delay: float = 1.0) -> T` — calls `fn()`, retrying on any exception with exponential backoff (`base_delay * 2**attempt` seconds between attempts), re-raising the last exception if all attempts fail. Consumed by Task 7 (Gemini vision), Task 9 (vector store — covers both Gemini embeddings and Mongo Atlas calls), and Task 10/11 (Gemini chat generation).

- [x] **Step 1: Write the failing tests**

```python
# tests/test_retry.py
from unittest.mock import MagicMock

import pytest

from app.retry import with_retries


def test_with_retries_returns_result_on_first_success():
    fn = MagicMock(return_value="ok")
    result = with_retries(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 1


def test_with_retries_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    fn = MagicMock(side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), "ok"])
    result = with_retries(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 3


def test_with_retries_raises_last_exception_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    fn = MagicMock(side_effect=RuntimeError("still failing"))
    with pytest.raises(RuntimeError, match="still failing"):
        with_retries(fn, max_attempts=3, base_delay=0)
    assert fn.call_count == 3
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_retry.py -v`
Expected: FAIL (`app.retry` doesn't exist).

- [x] **Step 3: Write `app/retry.py`**

```python
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retries(fn: Callable[[], T], max_attempts: int = 3, base_delay: float = 1.0) -> T:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # Gemini and MongoDB Atlas errors surface as plain exceptions from their clients
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2**attempt))
    raise last_exc
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_retry.py -v`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add app/retry.py tests/test_retry.py
git commit -m "feat: add retry-with-backoff helper for external service calls"
```

---

### Task 7: Gemini vision transcription for handwritten images + extraction dispatcher

**Files:**
- Modify: `app/extraction.py` (add `transcribe_image`, `extract_text`)
- Test: `tests/test_extraction_dispatch.py`

**Interfaces:**
- Consumes: `app.config.settings.gemini_api_key`, `app.retry.with_retries`.
- Produces: `transcribe_image(path: str) -> list[tuple[str, str]]`, `extract_text(path: str, content_type: str) -> list[tuple[str, str]]` (dispatches by MIME type; raises `ValueError` for unsupported types). Consumed by Task 10's `process_document`.

- [x] **Step 1: Write the failing tests (Gemini call is mocked — no real API key needed for this test)**

```python
# tests/test_extraction_dispatch.py
from unittest.mock import MagicMock, patch

import pytest

from app.extraction import extract_text


def test_extract_text_dispatches_pdf(tmp_path):
    import fitz

    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Ohm's Law")
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_text(str(pdf_path), "application/pdf")

    assert "Ohm" in pages[0][1]


def test_extract_text_dispatches_image_to_gemini(tmp_path):
    image_path = tmp_path / "notes.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    fake_response = MagicMock()
    fake_response.content = "F = ma"

    with patch("app.extraction.ChatGoogleGenerativeAI") as mock_llm_cls:
        mock_llm_cls.return_value.invoke.return_value = fake_response
        pages = extract_text(str(image_path), "image/jpeg")

    assert pages == [("scanned page", "F = ma")]


def test_extract_text_retries_gemini_call_on_transient_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    image_path = tmp_path / "notes.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    fake_response = MagicMock()
    fake_response.content = "F = ma"

    with patch("app.extraction.ChatGoogleGenerativeAI") as mock_llm_cls:
        mock_llm_cls.return_value.invoke.side_effect = [RuntimeError("timeout"), fake_response]
        pages = extract_text(str(image_path), "image/jpeg")

    assert pages == [("scanned page", "F = ma")]
    assert mock_llm_cls.return_value.invoke.call_count == 2


def test_extract_text_rejects_unsupported_type(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    with pytest.raises(ValueError):
        extract_text(str(path), "text/plain")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_extraction_dispatch.py -v`
Expected: FAIL (`extract_text` doesn't exist yet).

- [x] **Step 3: Add to `app/extraction.py`**

```python
import base64

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.retry import with_retries


def transcribe_image(path: str) -> list[tuple[str, str]]:
    with open(path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=settings.gemini_api_key)
    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Transcribe all handwritten and printed text in this image exactly as written. "
                    "Return only the transcribed text, no commentary."
                ),
            },
            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_data}"},
        ]
    )
    response = with_retries(lambda: llm.invoke([message]))
    text = response.content.strip()
    return [("scanned page", text)] if text else []


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def extract_text(path: str, content_type: str) -> list[tuple[str, str]]:
    if content_type == "application/pdf":
        return extract_pdf_pages(path)
    if content_type == DOCX_MIME:
        return extract_docx_sections(path)
    if content_type == PPTX_MIME:
        return extract_pptx_slides(path)
    if content_type.startswith("image/"):
        return transcribe_image(path)
    raise ValueError(f"Unsupported file type: {content_type}")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_extraction_dispatch.py -v`
Expected: PASS (4 passed)

- [x] **Step 5: Commit**

```bash
git add app/extraction.py tests/test_extraction_dispatch.py
git commit -m "feat: add Gemini vision transcription (with retry) and extraction dispatcher"
```

---

### Task 8: Chunking

**Files:**
- Create: `app/chunking.py`
- Test: `tests/test_chunking.py`

**Interfaces:**
- Produces: `chunk_pages(pages: list[tuple[str, str]], filename: str) -> list[dict]`. Each chunk dict: `{"chunk_id": str, "text": str, "filename": str, "source_label": str}`. Consumed by Task 9's `store_chunks` and Task 10's `process_document`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_chunking.py
from app.chunking import chunk_pages


def test_chunk_pages_produces_unique_chunk_ids():
    pages = [("page 1", "A" * 2000)]
    chunks = chunk_pages(pages, "textbook.pdf")
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert len(chunks) > 1  # 2000 chars should split into multiple chunks


def test_chunk_pages_preserves_source_label_and_filename():
    pages = [("page 5", "Short text")]
    chunks = chunk_pages(pages, "notes.docx")
    assert chunks[0]["source_label"] == "page 5"
    assert chunks[0]["filename"] == "notes.docx"
    assert chunks[0]["text"] == "Short text"


def test_chunk_pages_handles_multiple_pages():
    pages = [("page 1", "First page text"), ("page 2", "Second page text")]
    chunks = chunk_pages(pages, "book.pdf")
    labels = {c["source_label"] for c in chunks}
    assert labels == {"page 1", "page 2"}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_chunking.py -v`
Expected: FAIL (`app.chunking` doesn't exist).

- [x] **Step 3: Write `app/chunking.py`**

```python
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_pages(pages: list[tuple[str, str]], filename: str) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = []
    for source_label, text in pages:
        for piece in splitter.split_text(text):
            chunks.append(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "text": piece,
                    "filename": filename,
                    "source_label": source_label,
                }
            )
    return chunks
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_chunking.py -v`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add app/chunking.py tests/test_chunking.py
git commit -m "feat: add text chunking with unique chunk ids"
```

---

### Task 9: Embeddings, vector store (with retry), and Atlas Vector Search index setup

**Files:**
- Create: `app/embeddings.py`
- Create: `app/vectorstore.py`
- Create: `scripts/create_vector_index.py`
- Test: `tests/test_vectorstore.py`

**Interfaces:**
- Consumes: `app.config.settings.gemini_api_key`, `app.db.chunks_collection`, `app.retry.with_retries`.
- Produces: `get_embeddings() -> GoogleGenerativeAIEmbeddings`, `get_vectorstore(db) -> MongoDBAtlasVectorSearch`, `store_chunks(db, user_id, subject_id, document_id, chunks: list[dict]) -> None`, `similarity_search(db, user_id, subject_id, query, k=5) -> list[Document]` (each `Document.metadata` has `chunk_id`, `user_id`, `subject_id`, `document_id`, `filename`, `source_label`). Consumed by Task 10 (`store_chunks`) and Task 11 (`similarity_search`).

- [x] **Step 1: Write `app/embeddings.py`**

```python
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=settings.gemini_api_key)
```

- [x] **Step 2: Write the failing tests for `store_chunks` and `similarity_search` (mock the vector store — no real Atlas/Gemini call)**

```python
# tests/test_vectorstore.py
from unittest.mock import MagicMock, patch

from app.vectorstore import similarity_search, store_chunks


def test_store_chunks_builds_documents_with_full_metadata(db):
    chunks = [
        {"chunk_id": "c1", "text": "Ohm's Law: V = IR", "filename": "physics.pdf", "source_label": "page 3"},
    ]

    with patch("app.vectorstore.get_vectorstore") as mock_get_vectorstore:
        mock_store = MagicMock()
        mock_get_vectorstore.return_value = mock_store

        store_chunks(db, "user-1", "subject-1", "doc-1", chunks)

        added_docs = mock_store.add_documents.call_args[0][0]
        assert len(added_docs) == 1
        assert added_docs[0].page_content == "Ohm's Law: V = IR"
        assert added_docs[0].metadata == {
            "chunk_id": "c1",
            "user_id": "user-1",
            "subject_id": "subject-1",
            "document_id": "doc-1",
            "filename": "physics.pdf",
            "source_label": "page 3",
        }


def test_store_chunks_retries_on_transient_error(db, monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    chunks = [{"chunk_id": "c1", "text": "text", "filename": "a.pdf", "source_label": "page 1"}]

    with patch("app.vectorstore.get_vectorstore") as mock_get_vectorstore:
        mock_store = MagicMock()
        mock_store.add_documents.side_effect = [RuntimeError("timeout"), None]
        mock_get_vectorstore.return_value = mock_store

        store_chunks(db, "user-1", "subject-1", "doc-1", chunks)

        assert mock_store.add_documents.call_count == 2


def test_similarity_search_filters_by_user_and_subject(db):
    with patch("app.vectorstore.get_vectorstore") as mock_get_vectorstore:
        mock_store = MagicMock()
        mock_store.similarity_search.return_value = []
        mock_get_vectorstore.return_value = mock_store

        similarity_search(db, "user-1", "subject-1", "What is Ohm's Law?", k=5)

        mock_store.similarity_search.assert_called_once_with(
            "What is Ohm's Law?", k=5, pre_filter={"user_id": "user-1", "subject_id": "subject-1"}
        )
```

- [x] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_vectorstore.py -v`
Expected: FAIL (`app.vectorstore` doesn't exist).

- [x] **Step 4: Write `app/vectorstore.py`**

```python
from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo.database import Database

from app.db import chunks_collection
from app.embeddings import get_embeddings
from app.retry import with_retries

INDEX_NAME = "vector_index"


def get_vectorstore(db: Database) -> MongoDBAtlasVectorSearch:
    return MongoDBAtlasVectorSearch(
        collection=chunks_collection(db),
        embedding=get_embeddings(),
        index_name=INDEX_NAME,
        text_key="text",
        embedding_key="embedding",
    )


def store_chunks(db: Database, user_id: str, subject_id: str, document_id: str, chunks: list[dict]) -> None:
    vectorstore = get_vectorstore(db)
    docs = [
        Document(
            page_content=chunk["text"],
            metadata={
                "chunk_id": chunk["chunk_id"],
                "user_id": user_id,
                "subject_id": subject_id,
                "document_id": document_id,
                "filename": chunk["filename"],
                "source_label": chunk["source_label"],
            },
        )
        for chunk in chunks
    ]
    with_retries(lambda: vectorstore.add_documents(docs))


def similarity_search(db: Database, user_id: str, subject_id: str, query: str, k: int = 5) -> list[Document]:
    vectorstore = get_vectorstore(db)
    return with_retries(
        lambda: vectorstore.similarity_search(
            query, k=k, pre_filter={"user_id": user_id, "subject_id": subject_id}
        )
    )
```

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_vectorstore.py -v`
Expected: PASS (3 passed)

- [x] **Step 6: Write `scripts/create_vector_index.py`** (one-time manual setup script — Atlas Vector Search indexes can't be created against `mongomock`, and must exist before Task 10's real-Atlas testing works)

```python
from pymongo.operations import SearchIndexModel

from app.db import chunks_collection, get_db
from app.vectorstore import INDEX_NAME


def main():
    db = get_db()
    collection = chunks_collection(db)
    index_model = SearchIndexModel(
        definition={
            "fields": [
                {"type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine"},
                {"type": "filter", "path": "user_id"},
                {"type": "filter", "path": "subject_id"},
            ]
        },
        name=INDEX_NAME,
        type="vectorSearch",
    )
    collection.create_search_index(model=index_model)
    print(f"Created search index '{INDEX_NAME}' on {collection.full_name}")


if __name__ == "__main__":
    main()
```

- [x] **Step 7: Run the setup script against your real Atlas cluster**

Run: `.venv/Scripts/python scripts/create_vector_index.py` (requires a real `MONGODB_URI` and a Gemini-reachable network in `.env`; Atlas may take ~1 minute to finish building the index — check the Atlas UI's "Search" tab for status).

- [x] **Step 8: Commit**

```bash
git add app/embeddings.py app/vectorstore.py scripts/create_vector_index.py tests/test_vectorstore.py
git commit -m "feat: add Gemini embeddings, Atlas Vector Search store (with retry), and index setup script"
```

---

### Task 10: Document upload endpoint and background processing pipeline

**Files:**
- Create: `app/documents.py`
- Create: `app/templates/partials/_documents_list.html`
- Modify: `app/main.py` (include documents router)
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `app.extraction.extract_text`, `app.chunking.chunk_pages`, `app.vectorstore.store_chunks`, `app.auth.get_current_user`.
- Produces: `create_document(db, user_id, subject_id, filename) -> dict`, `list_documents(db, user_id, subject_id) -> list[dict]`, `mark_document(db, document_id, status, error=None) -> None`, `process_document(db, user_id, subject_id, document_id, path, content_type, filename) -> None`, `router`. Document dict shape: `{"_id": str, "user_id": str, "subject_id": str, "filename": str, "status": "processing"|"ready"|"failed", "error": str|None, "created_at": datetime}`. Consumed by Task 13's subject detail page.

Note: `extract_text` (Task 7) and `store_chunks` (Task 9) already retry transient Gemini/Atlas errors internally via `with_retries`; `process_document` only needs to catch the final exception after retries are exhausted and mark the document `failed`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_documents.py
from unittest.mock import patch

from app.documents import create_document, list_documents, mark_document, process_document


def test_create_document_starts_as_processing(db):
    doc = create_document(db, "user-1", "subject-1", "physics.pdf")
    assert doc["status"] == "processing"
    assert doc["error"] is None


def test_list_documents_scoped_to_user_and_subject(db):
    create_document(db, "user-1", "subject-1", "a.pdf")
    create_document(db, "user-1", "subject-2", "b.pdf")
    create_document(db, "user-2", "subject-1", "c.pdf")
    docs = list_documents(db, "user-1", "subject-1")
    assert len(docs) == 1
    assert docs[0]["filename"] == "a.pdf"


def test_mark_document_updates_status_and_error(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    mark_document(db, doc["_id"], "failed", "No readable text found")
    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "failed"
    assert updated["error"] == "No readable text found"


def test_process_document_marks_ready_on_success(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    with (
        patch("app.documents.extract_text", return_value=[("page 1", "some text")]),
        patch("app.documents.chunk_pages", return_value=[{"chunk_id": "c1", "text": "some text",
                                                             "filename": "a.pdf", "source_label": "page 1"}]),
        patch("app.documents.store_chunks") as mock_store,
    ):
        process_document(db, "user-1", "subject-1", doc["_id"], "/fake/path.pdf", "application/pdf", "a.pdf")

    mock_store.assert_called_once()
    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "ready"


def test_process_document_marks_failed_when_no_text_found(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    with patch("app.documents.extract_text", return_value=[]):
        process_document(db, "user-1", "subject-1", doc["_id"], "/fake/path.pdf", "application/pdf", "a.pdf")

    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "failed"
    assert "No readable text" in updated["error"]


def test_process_document_marks_failed_after_retries_exhausted(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    with patch("app.documents.extract_text", side_effect=RuntimeError("Gemini unavailable")):
        process_document(db, "user-1", "subject-1", doc["_id"], "/fake/path.pdf", "application/pdf", "a.pdf")

    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "failed"
    assert updated["error"] == "Gemini unavailable"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_documents.py -v`
Expected: FAIL (`app.documents` doesn't exist).

- [x] **Step 3: Write `app/documents.py`**

```python
import os
import shutil
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from pymongo.database import Database

from app.auth import get_current_user
from app.chunking import chunk_pages
from app.db import documents_collection, get_db
from app.extraction import extract_text
from app.templates import templates
from app.vectorstore import store_chunks

router = APIRouter()
UPLOAD_ROOT = "uploads"


def create_document(db: Database, user_id: str, subject_id: str, filename: str) -> dict:
    document = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "subject_id": subject_id,
        "filename": filename,
        "status": "processing",
        "error": None,
        "created_at": datetime.now(timezone.utc),
    }
    documents_collection(db).insert_one(document)
    return document


def list_documents(db: Database, user_id: str, subject_id: str) -> list[dict]:
    return list(
        documents_collection(db)
        .find({"user_id": user_id, "subject_id": subject_id})
        .sort("created_at", -1)
    )


def mark_document(db: Database, document_id: str, status: str, error: str | None = None) -> None:
    documents_collection(db).update_one({"_id": document_id}, {"$set": {"status": status, "error": error}})


def save_upload(user_id: str, subject_id: str, document_id: str, upload: UploadFile) -> str:
    folder = os.path.join(UPLOAD_ROOT, user_id, subject_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{document_id}_{upload.filename}")
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return path


def process_document(
    db: Database, user_id: str, subject_id: str, document_id: str, path: str, content_type: str, filename: str
) -> None:
    try:
        pages = extract_text(path, content_type)
        if not pages:
            mark_document(db, document_id, "failed", "No readable text found in file")
            return
        chunks = chunk_pages(pages, filename)
        store_chunks(db, user_id, subject_id, document_id, chunks)
        mark_document(db, document_id, "ready")
    except Exception as exc:
        # extract_text and store_chunks already retried transient Gemini/Atlas errors internally;
        # reaching here means retries were exhausted or the error is non-transient (e.g. corrupt file).
        mark_document(db, document_id, "failed", str(exc))


@router.post("/subjects/{subject_id}/documents")
def upload_document(
    subject_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
    user: dict = Depends(get_current_user),
):
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
    return {"document_id": document["_id"], "status": "processing"}


@router.get("/subjects/{subject_id}/documents/list")
def documents_list_partial(
    subject_id: str,
    request: Request,
    db: Database = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    documents = list_documents(db, user["_id"], subject_id)
    return templates.TemplateResponse(request, "partials/_documents_list.html", {"documents": documents})
```

- [x] **Step 4: Write `app/templates/partials/_documents_list.html`**

```html
<ul>
{% for doc in documents %}
  <li>{{ doc.filename }} — {{ doc.status }}{% if doc.error %} ({{ doc.error }}){% endif %}</li>
{% endfor %}
</ul>
```

- [x] **Step 5: Modify `app/main.py` to include the documents router**

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.documents import router as documents_router
from app.subjects import router as subjects_router

app = FastAPI(title="Exam Partner")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.include_router(auth_router)
app.include_router(subjects_router)
app.include_router(documents_router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [x] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_documents.py -v`
Expected: PASS (6 passed)

- [x] **Step 7: Commit**

```bash
git add app/documents.py app/templates/partials/_documents_list.html app/main.py tests/test_documents.py
git commit -m "feat: add document upload with background extraction/chunking/embedding pipeline"
```

---

### Task 11: RAG retrieval chain (answer with mandatory citations)

**Files:**
- Create: `app/rag_chain.py`
- Test: `tests/test_rag_chain.py`

**Interfaces:**
- Consumes: `app.vectorstore.similarity_search`, `app.config.settings.gemini_api_key`, `app.retry.with_retries`.
- Produces: `answer_question(db, user_id, subject_id, question) -> dict` with shape `{"answer": str, "citations": list[{"filename": str, "source_label": str}], "response_mode": "rag", "found": bool}`. Consumed by Task 13's chat endpoint.

- [x] **Step 1: Write the failing tests (LLM and retrieval are mocked)**

```python
# tests/test_rag_chain.py
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.rag_chain import answer_question


def _fake_doc(text, filename, source_label):
    return Document(page_content=text, metadata={"filename": filename, "source_label": source_label})


def test_answer_question_returns_grounded_answer_with_citations(db):
    retrieved = [_fake_doc("Ohm's Law: V = IR", "physics.pdf", "page 3")]
    fake_response = MagicMock()
    fake_response.content = "Ohm's Law states that V = IR."

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.invoke.return_value = fake_response
        result = answer_question(db, "user-1", "subject-1", "What is Ohm's Law?")

    assert result["found"] is True
    assert result["response_mode"] == "rag"
    assert result["answer"] == "Ohm's Law states that V = IR."
    assert result["citations"] == [{"filename": "physics.pdf", "source_label": "page 3"}]


def test_answer_question_reports_not_found_when_llm_signals_it(db):
    retrieved = [_fake_doc("Unrelated content", "physics.pdf", "page 1")]
    fake_response = MagicMock()
    fake_response.content = "NOT_FOUND_IN_MATERIAL"

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.invoke.return_value = fake_response
        result = answer_question(db, "user-1", "subject-1", "What is quantum entanglement?")

    assert result["found"] is False
    assert result["citations"] == []
    assert "Not found" in result["answer"]


def test_answer_question_reports_not_found_when_no_chunks_retrieved(db):
    with patch("app.rag_chain.similarity_search", return_value=[]):
        result = answer_question(db, "user-1", "subject-1", "What is quantum entanglement?")

    assert result["found"] is False
    assert result["citations"] == []


def test_answer_question_retries_gemini_call_on_transient_error(db, monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    retrieved = [_fake_doc("Ohm's Law: V = IR", "physics.pdf", "page 3")]
    fake_response = MagicMock()
    fake_response.content = "Ohm's Law states that V = IR."

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.invoke.side_effect = [RuntimeError("timeout"), fake_response]
        result = answer_question(db, "user-1", "subject-1", "What is Ohm's Law?")

    assert result["found"] is True
    assert mock_get_llm.return_value.invoke.call_count == 2
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_rag_chain.py -v`
Expected: FAIL (`app.rag_chain` doesn't exist).

- [x] **Step 3: Write `app/rag_chain.py`**

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from pymongo.database import Database

from app.config import settings
from app.retry import with_retries
from app.vectorstore import similarity_search

NOT_FOUND_MARKER = "NOT_FOUND_IN_MATERIAL"

SYSTEM_PROMPT = (
    "You are a study assistant. Answer the question using ONLY the context below, "
    "which comes from the student's own uploaded material. "
    f"If the answer is not contained in the context, respond with exactly: {NOT_FOUND_MARKER}\n\n"
    "Context:\n{context}"
)


def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=settings.gemini_api_key)


def answer_question(db: Database, user_id: str, subject_id: str, question: str) -> dict:
    results = similarity_search(db, user_id, subject_id, question, k=5)
    if not results:
        return {"answer": "Not found in your uploaded material.", "citations": [], "response_mode": "rag", "found": False}

    context = "\n\n".join(doc.page_content for doc in results)
    prompt = SYSTEM_PROMPT.format(context=context) + f"\n\nQuestion: {question}"
    llm = get_llm()
    response = with_retries(lambda: llm.invoke(prompt))
    answer = response.content.strip()

    if NOT_FOUND_MARKER in answer:
        return {"answer": "Not found in your uploaded material.", "citations": [], "response_mode": "rag", "found": False}

    citations = [
        {"filename": doc.metadata["filename"], "source_label": doc.metadata["source_label"]} for doc in results[:3]
    ]
    return {"answer": answer, "citations": citations, "response_mode": "rag", "found": True}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_rag_chain.py -v`
Expected: PASS (4 passed)

- [x] **Step 5: Commit**

```bash
git add app/rag_chain.py tests/test_rag_chain.py
git commit -m "feat: add RAG retrieval chain with mandatory citations, retry, and not-found detection"
```

---

### Task 12: General AI fallback mode

**Files:**
- Modify: `app/rag_chain.py` (add `answer_general`)
- Modify: `tests/test_rag_chain.py`

**Interfaces:**
- Produces: `answer_general(question: str) -> dict` with shape `{"answer": str, "citations": [], "response_mode": "general", "found": True}`. Consumed by Task 13's chat endpoint.

- [x] **Step 1: Add the failing test**

```python
# append to tests/test_rag_chain.py
from unittest.mock import MagicMock, patch

from app.rag_chain import answer_general


def test_answer_general_has_no_citations_and_general_mode():
    fake_response = MagicMock()
    fake_response.content = "Quantum entanglement is a phenomenon where..."

    with patch("app.rag_chain.get_llm") as mock_get_llm:
        mock_get_llm.return_value.invoke.return_value = fake_response
        result = answer_general("What is quantum entanglement?")

    assert result["response_mode"] == "general"
    assert result["citations"] == []
    assert result["found"] is True
    assert "entanglement" in result["answer"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_rag_chain.py::test_answer_general_has_no_citations_and_general_mode -v`
Expected: FAIL (`answer_general` doesn't exist).

- [x] **Step 3: Add to `app/rag_chain.py`**

```python
def answer_general(question: str) -> dict:
    llm = get_llm()
    response = with_retries(lambda: llm.invoke(question))
    return {"answer": response.content.strip(), "citations": [], "response_mode": "general", "found": True}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_rag_chain.py -v`
Expected: PASS (5 passed)

- [x] **Step 5: Commit**

```bash
git add app/rag_chain.py tests/test_rag_chain.py
git commit -m "feat: add general AI fallback mode (unsourced, explicitly opt-in)"
```

---

### Task 13: Chat endpoint and history persistence

**Files:**
- Create: `app/chat.py`
- Create: `app/templates/partials/_message.html`
- Modify: `app/main.py` (include chat router)
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: `app.rag_chain.answer_question`, `app.rag_chain.answer_general`, `app.auth.get_current_user`.
- Produces: `save_chat_message(db, user_id, subject_id, question, result: dict) -> dict`, `list_chat_history(db, user_id, subject_id) -> list[dict]`, `router`. Chat message dict shape: `{"_id": str, "user_id": str, "subject_id": str, "question": str, "answer": str, "citations": list[dict], "response_mode": "rag"|"general", "created_at": datetime}`. Consumed by Task 14's subject detail page.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_chat.py
from unittest.mock import patch

from app.chat import list_chat_history, save_chat_message


def test_save_chat_message_records_response_mode_and_citations(db):
    result = {
        "answer": "Ohm's Law states V = IR.",
        "citations": [{"filename": "physics.pdf", "source_label": "page 3"}],
        "response_mode": "rag",
        "found": True,
    }
    message = save_chat_message(db, "user-1", "subject-1", "What is Ohm's Law?", result)
    assert message["response_mode"] == "rag"
    assert message["citations"] == [{"filename": "physics.pdf", "source_label": "page 3"}]


def test_list_chat_history_scoped_to_user_and_subject(db):
    result = {"answer": "answer", "citations": [], "response_mode": "general", "found": True}
    save_chat_message(db, "user-1", "subject-1", "q1", result)
    save_chat_message(db, "user-2", "subject-1", "q2", result)
    history = list_chat_history(db, "user-1", "subject-1")
    assert len(history) == 1
    assert history[0]["question"] == "q1"


def test_ask_question_endpoint_saves_rag_response(authed_client, db):
    from app.subjects import create_subject

    client, user = authed_client
    subject = create_subject(db, user["_id"], "Physics")

    fake_result = {"answer": "V = IR", "citations": [{"filename": "p.pdf", "source_label": "page 1"}],
                    "response_mode": "rag", "found": True}
    with patch("app.chat.answer_question", return_value=fake_result):
        response = client.post(f"/subjects/{subject['_id']}/chat", data={"question": "What is Ohm's Law?"})

    assert response.status_code == 200
    history = list_chat_history(db, user["_id"], subject["_id"])
    assert len(history) == 1
    assert history[0]["response_mode"] == "rag"


def test_ask_general_endpoint_saves_general_response(authed_client, db):
    from app.subjects import create_subject

    client, user = authed_client
    subject = create_subject(db, user["_id"], "Physics")

    fake_result = {"answer": "General answer", "citations": [], "response_mode": "general", "found": True}
    with patch("app.chat.answer_general", return_value=fake_result):
        response = client.post(f"/subjects/{subject['_id']}/chat/general", data={"question": "anything"})

    assert response.status_code == 200
    history = list_chat_history(db, user["_id"], subject["_id"])
    assert history[0]["response_mode"] == "general"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_chat.py -v`
Expected: FAIL (`app.chat` doesn't exist).

- [x] **Step 3: Write `app/chat.py`**

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from pymongo.database import Database

from app.auth import get_current_user
from app.db import chats_collection, get_db
from app.rag_chain import answer_general, answer_question
from app.templates import templates

router = APIRouter()


def save_chat_message(db: Database, user_id: str, subject_id: str, question: str, result: dict) -> dict:
    message = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "subject_id": subject_id,
        "question": question,
        "answer": result["answer"],
        "citations": result["citations"],
        "response_mode": result["response_mode"],
        "created_at": datetime.now(timezone.utc),
    }
    chats_collection(db).insert_one(message)
    return message


def list_chat_history(db: Database, user_id: str, subject_id: str) -> list[dict]:
    return list(
        chats_collection(db).find({"user_id": user_id, "subject_id": subject_id}).sort("created_at", 1)
    )


@router.post("/subjects/{subject_id}/chat")
def ask_question(
    subject_id: str,
    request: Request,
    question: str = Form(...),
    db: Database = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = answer_question(db, user["_id"], subject_id, question)
    message = save_chat_message(db, user["_id"], subject_id, question, result)
    return templates.TemplateResponse(request, "partials/_message.html", {"msg": message})


@router.post("/subjects/{subject_id}/chat/general")
def ask_general(
    subject_id: str,
    request: Request,
    question: str = Form(...),
    db: Database = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = answer_general(question)
    message = save_chat_message(db, user["_id"], subject_id, question, result)
    return templates.TemplateResponse(request, "partials/_message.html", {"msg": message})
```

- [x] **Step 4: Write `app/templates/partials/_message.html`**

```html
<div class="message">
  <p><strong>Q:</strong> {{ msg.question }}</p>
  <p><strong>A ({{ msg.response_mode }}):</strong> {{ msg.answer }}</p>
  {% if msg.citations %}
  <ul class="citations">
    {% for c in msg.citations %}<li>{{ c.filename }} — {{ c.source_label }}</li>{% endfor %}
  </ul>
  {% endif %}
  {% if msg.response_mode == "rag" and not msg.citations %}
  <form hx-post="/subjects/{{ msg.subject_id }}/chat/general" hx-target="#chat-history" hx-swap="beforeend">
    <input type="hidden" name="question" value="{{ msg.question }}">
    <button type="submit">Get a general AI answer instead</button>
  </form>
  {% endif %}
</div>
```

- [x] **Step 5: Modify `app/main.py` to include the chat router**

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.chat import router as chat_router
from app.config import settings
from app.documents import router as documents_router
from app.subjects import router as subjects_router

app = FastAPI(title="Exam Partner")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.include_router(auth_router)
app.include_router(subjects_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [x] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_chat.py -v`
Expected: PASS (4 passed)

- [x] **Step 7: Commit**

```bash
git add app/chat.py app/templates/partials/_message.html app/main.py tests/test_chat.py
git commit -m "feat: add chat endpoint with response_mode-tagged history persistence"
```

---

### Task 14: Subject detail page wiring (documents + chat UI together)

**Files:**
- Create: `app/templates/subject_detail.html`
- Modify: `app/subjects.py` (add subject detail route)
- Test: `tests/test_subject_detail.py`

**Interfaces:**
- Consumes: `app.subjects.get_subject`, `app.documents.list_documents`, `app.chat.list_chat_history`.
- Produces: `GET /subjects/{subject_id}` page route (404s via `HTTPException` if the subject doesn't belong to the user).

- [x] **Step 1: Write the failing tests**

```python
# tests/test_subject_detail.py
from app.subjects import create_subject


def test_subject_detail_page_shows_subject_name(authed_client, db):
    client, user = authed_client
    subject = create_subject(db, user["_id"], "Thermodynamics")

    response = client.get(f"/subjects/{subject['_id']}")

    assert response.status_code == 200
    assert "Thermodynamics" in response.text


def test_subject_detail_page_404s_for_other_users_subject(authed_client, db):
    client, user = authed_client
    other_subject = create_subject(db, "some-other-user-id", "Not Yours")

    response = client.get(f"/subjects/{other_subject['_id']}")

    assert response.status_code == 404
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_subject_detail.py -v`
Expected: FAIL (404 route doesn't exist / no template).

- [x] **Step 3: Write `app/templates/subject_detail.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ subject.name }}</h1>

<h2>Documents</h2>
<form hx-post="/subjects/{{ subject._id }}/documents" hx-encoding="multipart/form-data"
      hx-target="#doc-list" hx-swap="innerHTML">
  <input type="file" name="file" required>
  <button type="submit">Upload</button>
</form>
<div id="doc-list" hx-get="/subjects/{{ subject._id }}/documents/list" hx-trigger="load, every 3s" hx-swap="innerHTML"></div>

<h2>Chat</h2>
<div id="chat-history">
  {% for msg in history %}
    {% include "partials/_message.html" %}
  {% endfor %}
</div>
<form hx-post="/subjects/{{ subject._id }}/chat" hx-target="#chat-history" hx-swap="beforeend">
  <input type="text" name="question" placeholder="Ask a question" required>
  <button type="submit">Ask</button>
</form>
{% endblock %}
```

- [x] **Step 4: Add the subject detail route to `app/subjects.py`**

```python
# add these imports at the top of app/subjects.py
from fastapi import HTTPException

from app.chat import list_chat_history
from app.documents import list_documents

# add this route below the existing ones
@router.get("/subjects/{subject_id}")
def subject_detail_page(
    subject_id: str, request: Request, db: Database = Depends(get_db), user: dict = Depends(get_current_user)
):
    subject = get_subject(db, user["_id"], subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    documents = list_documents(db, user["_id"], subject_id)
    history = list_chat_history(db, user["_id"], subject_id)
    return templates.TemplateResponse(
        request, "subject_detail.html", {"subject": subject, "documents": documents, "history": history}
    )
```

Note: `app/chat.py` and `app/documents.py` don't import from `app/subjects.py`, so this import direction (subjects → chat, documents) doesn't create a circular import. Chat message dicts from `list_chat_history` already include `subject_id` (Task 13's `save_chat_message` stores it), so `partials/_message.html`'s `msg.subject_id` reference already resolves correctly.

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_subject_detail.py -v`
Expected: PASS (2 passed)

- [x] **Step 6: Run the full test suite**

Run: `.venv/Scripts/pytest -v`
Expected: PASS (all tests across all tasks)

- [x] **Step 7: Commit**

```bash
git add app/templates/subject_detail.html app/subjects.py tests/test_subject_detail.py
git commit -m "feat: wire subject detail page with document upload and chat"
```

---

### Task 15: Manual end-to-end verification

**Files:** None (manual QA against the real running app with real credentials — no code changes).

- [x] **Step 1: Fill in real credentials in `.env`**

Set a real `MONGODB_URI` (Atlas cluster with the `vector_index` created in Task 9), a real `GEMINI_API_KEY`, and a random `SESSION_SECRET`.

- [x] **Step 2: Start the app**

Run: `.venv/Scripts/uvicorn app.main:app --reload`

- [x] **Step 3: Sign up and create a subject**

Visit `http://localhost:8000/signup`, create an account, create a subject (e.g. "Physics").

- [x] **Step 4: Upload a typed PDF**

Upload a real textbook/notes PDF. Confirm the document status moves from `processing` to `ready` within the polling interval (check the Atlas UI's `chunks` collection to confirm chunks were inserted with `embedding` fields).

- [x] **Step 5: Upload a handwritten note photo**

Upload a photo of a handwritten page. Confirm it also reaches `ready` and that the transcribed chunks look reasonable (spot-check in Atlas).

- [x] **Step 6: Ask a question answerable from the uploaded material**

Confirm the answer is grounded, includes citations naming the correct file/page, and `response_mode` is `rag` (check the `chats` collection in Atlas).

- [x] **Step 7: Ask a question NOT covered by the uploaded material**

Confirm the UI shows "Not found in your uploaded material" and offers "Get a general AI answer instead"; confirm clicking it returns an answer with no citations and `response_mode` `general`.

- [x] **Step 8: Verify user/subject isolation**

Sign up as a second user, create a subject with the same name, upload a different document, and confirm questions in that subject never return citations or content from the first user's material.

- [x] **Step 9: Note results**

If any step fails, file it as a follow-up fix — do not mark this task's checkbox complete until all 8 steps pass against the real Atlas + Gemini backend.
