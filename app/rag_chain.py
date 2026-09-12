from langchain_google_genai import ChatGoogleGenerativeAI
from pymongo.database import Database

from app.config import settings
from app.llm_response import text_from_response
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
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=settings.gemini_api_key)


def answer_question(db: Database, user_id: str, subject_id: str, question: str) -> dict:
    results = similarity_search(db, user_id, subject_id, question, k=5)
    if not results:
        return {"answer": "Not found in your uploaded material.", "citations": [], "response_mode": "rag", "found": False}

    context = "\n\n".join(doc.page_content for doc in results)
    prompt = SYSTEM_PROMPT.format(context=context) + f"\n\nQuestion: {question}"
    llm = get_llm()
    response = with_retries(lambda: llm.invoke(prompt))
    answer = text_from_response(response)

    if NOT_FOUND_MARKER in answer:
        return {"answer": "Not found in your uploaded material.", "citations": [], "response_mode": "rag", "found": False}

    citations = [
        {"filename": doc.metadata["filename"], "source_label": doc.metadata["source_label"]} for doc in results[:3]
    ]
    return {"answer": answer, "citations": citations, "response_mode": "rag", "found": True}


def answer_general(question: str) -> dict:
    llm = get_llm()
    response = with_retries(lambda: llm.invoke(question))
    return {"answer": text_from_response(response), "citations": [], "response_mode": "general", "found": True}
