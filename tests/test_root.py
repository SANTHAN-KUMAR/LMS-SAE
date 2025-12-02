def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("name")
    assert data.get("version")
    assert data.get("documentation") == "/docs"
