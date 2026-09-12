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
