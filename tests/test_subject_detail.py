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
