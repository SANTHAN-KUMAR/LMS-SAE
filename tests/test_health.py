def test_health_route_group_root(client):
    # Router mounted at /health, router root at '/'
    resp = client.get("/health/")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("name")
    assert data.get("version")


def test_health_check_endpoint(client):
    # The health check is defined at '/health' inside the router,
    # and the router is included with prefix '/health' -> '/health/health'
    resp = client.get("/health/health")
    # In case DB/Moodle are unavailable, endpoint should still return 200 with status field
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "database" in data
    assert "moodle_connection" in data
