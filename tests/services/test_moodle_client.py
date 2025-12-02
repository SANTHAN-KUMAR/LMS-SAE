import asyncio
import httpx
import pytest
from app.services.moodle_client import MoodleClient, MoodleAPIError


class DummyResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise httpx.HTTPStatusError("bad", request=None, response=self)


@pytest.mark.asyncio
async def test_get_token_success(monkeypatch):
    mc = MoodleClient(base_url="https://example.com")

    async def fake_post(url, data=None):
        return DummyResponse({"token": "abc123"}, 200)

    client = await mc._get_client()
    monkeypatch.setattr(client, "post", fake_post)

    res = await mc.get_token("user", "pass")
    assert res["token"] == "abc123"


@pytest.mark.asyncio
async def test_get_token_error(monkeypatch):
    mc = MoodleClient(base_url="https://example.com")

    async def fake_post(url, data=None):
        return DummyResponse({"error": "Invalid login"}, 200)

    client = await mc._get_client()
    monkeypatch.setattr(client, "post", fake_post)

    with pytest.raises(MoodleAPIError):
        await mc.get_token("user", "badpass")
