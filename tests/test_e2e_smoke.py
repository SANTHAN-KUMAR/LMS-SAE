def test_e2e_smoke_flow(client):
    # Root
    r = client.get("/")
    assert r.status_code == 200
    # Health config path under router
    r = client.get("/health/config")
    assert r.status_code == 200
    conf = r.json()
    assert "app_name" in conf and "app_version" in conf
    # Health check - should respond even if degraded
    r = client.get("/health/health")
    assert r.status_code == 200
    hc = r.json()
    assert "status" in hc
    # Protected route should block without auth
    r = client.get("/student/dashboard")
    assert r.status_code in (401, 403, 404, 422)
