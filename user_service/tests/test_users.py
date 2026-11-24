"""Тести ролей user, auditor, admin для маршрутів User Service."""


def test_user_can_view_own_profile(client, user):
    response = client.get(f"/user/{user['id']}", headers=user["headers"])
    assert response.status_code == 200
    assert response.json()["role"] == "user"


def test_user_cannot_view_other_profile(client, user, other_user):
    response = client.get(f"/user/{other_user['id']}", headers=user["headers"])
    assert response.status_code == 404


def test_user_cannot_use_admin_routes(client, user, other_user):
    assert client.get("/users", headers=user["headers"]).status_code == 403
    assert client.delete(f"/user/{other_user['id']}", headers=user["headers"]).status_code == 403
    response = client.patch(f"/user/{user['id']}/role", headers=user["headers"], json={"role": "admin"})
    assert response.status_code == 403


def test_auditor_can_read_users(client, user, auditor):
    assert client.get("/users", headers=auditor["headers"]).status_code == 200
    assert client.get(f"/user/{user['id']}", headers=auditor["headers"]).status_code == 200


def test_auditor_cannot_write_users(client, user, auditor):
    headers = auditor["headers"]
    assert client.delete(f"/user/{user['id']}", headers=headers).status_code == 403
    assert client.patch(f"/user/{user['id']}/role", headers=headers, json={"role": "admin"}).status_code == 403


def test_admin_changes_role(client, user, admin):
    response = client.patch(f"/user/{user['id']}/role", headers=admin["headers"], json={"role": "auditor"})
    assert response.status_code == 200
    assert response.json()["role"] == "auditor"
    # нова роль діє одразу: auditor може читати список, але не змінювати його
    assert client.get("/users", headers=user["headers"]).status_code == 200
    assert client.delete(f"/user/{user['id']}", headers=user["headers"]).status_code == 403


def test_admin_cannot_set_unknown_role(client, user, admin):
    response = client.patch(f"/user/{user['id']}/role", headers=admin["headers"], json={"role": "superuser"})
    assert response.status_code == 400


def test_admin_can_delete_user(client, user, admin):
    assert client.delete(f"/user/{user['id']}", headers=admin["headers"]).status_code == 204
    assert client.delete(f"/user/{user['id']}", headers=admin["headers"]).status_code == 404


def test_admin_has_full_access_to_users(client, user, other_user, admin):
    assert client.get("/users", headers=admin["headers"]).status_code == 200
    assert client.get(f"/user/{other_user['id']}", headers=admin["headers"]).status_code == 200
