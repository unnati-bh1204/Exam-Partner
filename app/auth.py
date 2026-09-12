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
