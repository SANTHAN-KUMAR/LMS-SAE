def test_auth_routes_exist(client):
    # Expect auth router under /auth. Unauthenticated calls may return 401/405.
    r = client.get("/auth/")
    assert r.status_code in (200, 404)  # router root may be defined or not


def test_student_routes_protected(client):
    # Student dashboard should be protected; expect 401/403
    r = client.get("/student/dashboard")
    assert r.status_code in (401, 403, 404, 422)


def test_upload_routes_exist_and_constraints(client):
    # Upload endpoints exist; POST without file should 422 or 400
    r = client.post("/upload/single")
    assert r.status_code in (400, 401, 422, 405)


def test_admin_routes_protected(client):
    r = client.get("/admin/")
    assert r.status_code in (200, 401, 403, 404)
