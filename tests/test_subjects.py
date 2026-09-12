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
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_create_subject_via_form(authed_client):
    client, user = authed_client
    response = client.post("/subjects", data={"name": "Thermodynamics"}, follow_redirects=False)
    assert response.status_code == 303
    response = client.get("/subjects")
    assert "Thermodynamics" in response.text
