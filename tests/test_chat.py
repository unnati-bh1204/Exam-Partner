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
