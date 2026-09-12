import pytest
from langchain_google_genai._common import GoogleGenerativeAIError
from pymongo.errors import ServerSelectionTimeoutError

from app.db import get_db
from app.main import app


@pytest.fixture
def outage_client(client):
    """A client whose database dependency fails the way a paused Atlas cluster does."""
    previous = app.dependency_overrides.get(get_db)

    def unreachable_db():
        raise ServerSelectionTimeoutError("SSL handshake failed: no reachable servers")

    app.dependency_overrides[get_db] = unreachable_db
    yield client
    if previous is not None:
        app.dependency_overrides[get_db] = previous


def test_login_during_database_outage_shows_a_readable_page(outage_client):
    response = outage_client.post(
        "/login", data={"email": "a@b.com", "password": "password123"}, follow_redirects=False
    )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("text/html")
    assert "Internal Server Error" not in response.text
    assert "database" in response.text.lower()


def test_dashboard_during_database_outage_shows_a_readable_page(outage_client):
    response = outage_client.get("/subjects", follow_redirects=False)
    assert response.status_code == 503
    assert "database" in response.text.lower()


def test_htmx_request_during_outage_returns_a_fragment_not_a_whole_page(outage_client):
    response = outage_client.get(
        "/subjects/any/documents/list", headers={"HX-Request": "true"}
    )
    assert response.status_code == 503
    # A full page injected into a polling target would wreck the layout.
    assert "<!DOCTYPE html>" not in response.text
    assert "database" in response.text.lower()


def test_ai_quota_error_during_chat_shows_a_readable_message(authed_client, monkeypatch):
    client, user = authed_client
    from app.subjects import create_subject
    from app.db import get_db as real_get_db

    subject = create_subject(app.dependency_overrides[real_get_db](), user["_id"], "Physics")

    def exhausted(*args, **kwargs):
        raise GoogleGenerativeAIError(
            "Error calling model (RESOURCE_EXHAUSTED): 429 You exceeded your current quota."
        )

    monkeypatch.setattr("app.chat.answer_question", exhausted)

    response = client.post(
        f"/subjects/{subject['_id']}/chat",
        data={"question": "hi"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 503
    assert "<!DOCTYPE html>" not in response.text
    assert "limit" in response.text.lower()
