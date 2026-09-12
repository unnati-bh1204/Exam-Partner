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
