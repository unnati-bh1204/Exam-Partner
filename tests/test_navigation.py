def test_root_redirects_to_subjects_when_logged_in(authed_client):
    client, _ = authed_client
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_root_redirects_to_login_when_logged_out(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
