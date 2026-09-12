import re

from langchain_google_genai import ChatGoogleGenerativeAI
from pymongo.database import Database

from app.config import settings
from app.llm_response import text_from_response
from app.retry import with_retries
from app.vectorstore import similarity_search

NOT_FOUND_MARKER = "NOT_FOUND_IN_MATERIAL"

SYSTEM_PROMPT = (
    "You are a study assistant. Answer the question using ONLY the numbered context "
    "below, which comes from the student's own uploaded material.\n\n"
    f"If the answer is not contained in the context, respond with exactly: {NOT_FOUND_MARKER}\n\n"
    "Otherwise, answer the question, then end your reply with a final line listing the "
    "numbers of the passages you actually used, like:\n"
    "SOURCES: 1, 4\n\n"
    "Context:\n{context}"
)

# Trailing "SOURCES: 1, 4" line the model is asked to append.
SOURCES_LINE = re.compile(r"^\s*SOURCES\s*:\s*([\d,\s]+)\s*$", re.IGNORECASE | re.MULTILINE)


def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=settings.gemini_api_key)


def _not_found() -> dict:
    return {
        "answer": "Not found in your uploaded material.",
        "citations": [],
        "response_mode": "rag",
        "found": False,
    }


def _cite(doc) -> dict:
    return {"filename": doc.metadata["filename"], "source_label": doc.metadata["source_label"]}


def _split_sources(answer: str, results: list) -> tuple[str, list[dict]]:
    """Separate the model's trailing SOURCES line from its answer.

    Returns the cleaned answer plus citations for the passages it named. Falls
    back to the strongest matches when the model omits the line, so an answer is
    never left uncited.
    """
    match = SOURCES_LINE.search(answer)
    if not match:
        return answer.strip(), _dedupe(_cite(d) for d in results[:3])

    cleaned = (answer[: match.start()] + answer[match.end() :]).strip()

    cited = []
    for raw in match.group(1).split(","):
        raw = raw.strip()
        if not raw.isdigit():
            continue
        index = int(raw) - 1  # the prompt numbers passages from 1
        if 0 <= index < len(results):
            cited.append(_cite(results[index]))

    if not cited:
        cited = [_cite(d) for d in results[:3]]
    return cleaned, _dedupe(cited)


def _dedupe(citations) -> list[dict]:
    seen, unique = set(), []
    for citation in citations:
        key = (citation["filename"], citation["source_label"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


def answer_question(db: Database, user_id: str, subject_id: str, question: str) -> dict:
    # A subject is often a single dense document whose chunks are all topically
    # similar, so a narrow window can rank specific sections above the passage
    # that actually defines the topic. Retrieve wider and let the model choose.
    results = similarity_search(db, user_id, subject_id, question, k=12)
    if not results:
        return _not_found()

    context = "\n\n".join(f"[{i}] {doc.page_content}" for i, doc in enumerate(results, start=1))
    prompt = SYSTEM_PROMPT.format(context=context) + f"\n\nQuestion: {question}"
    llm = get_llm()
    response = with_retries(lambda: llm.invoke(prompt))
    answer = text_from_response(response)

    if NOT_FOUND_MARKER in answer:
        return _not_found()

    answer, citations = _split_sources(answer, results)
    return {"answer": answer, "citations": citations, "response_mode": "rag", "found": True}


def answer_general(question: str) -> dict:
    llm = get_llm()
    response = with_retries(lambda: llm.invoke(question))
    return {"answer": text_from_response(response), "citations": [], "response_mode": "general", "found": True}
