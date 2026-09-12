import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.auth import get_current_user
from app.chat import list_chat_history
from app.db import get_db, subjects_collection
from app.documents import list_documents
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


def summarise_subjects(db: Database, user_id: str) -> list[dict]:
    """Subject records plus the counts the dashboard cards display.

    Presentation data only — no change to how subjects are stored or queried.
    """
    summaries = []
    for subject in list_subjects(db, user_id):
        documents = list_documents(db, user_id, subject["_id"])
        timestamps = [d["created_at"] for d in documents if d.get("created_at")]
        summaries.append(
            {
                **subject,
                "document_count": len(documents),
                "ready_count": sum(1 for d in documents if d["status"] == "ready"),
                "processing_count": sum(1 for d in documents if d["status"] == "processing"),
                "failed_count": sum(1 for d in documents if d["status"] == "failed"),
                "last_activity": max(timestamps) if timestamps else subject.get("created_at"),
            }
        )
    return summaries


@router.get("/subjects")
def subjects_page(request: Request, db: Database = Depends(get_db), user: dict = Depends(get_current_user)):
    subjects = summarise_subjects(db, user["_id"])
    total_documents = sum(s["document_count"] for s in subjects)
    return templates.TemplateResponse(
        request,
        "subjects.html",
        {"subjects": subjects, "user": user, "total_documents": total_documents},
    )


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
        request,
        "subject_detail.html",
        {"subject": subject, "documents": documents, "history": history, "user": user},
    )
