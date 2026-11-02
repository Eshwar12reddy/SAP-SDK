from app.database import MemoryEntry
from tests.conftest import register_and_login


async def _seed(client, text="Prefers concise answers"):
    async with client.sessions() as s:
        s.add(MemoryEntry(user_id=1, memory_text=text))
        await s.commit()


async def test_memory_settings_toggle_and_listing(client):
    h = await register_and_login(client)
    assert (await client.get("/api/memory/settings", headers=h)).json() == {"enabled": True}
    assert (await client.put("/api/memory/settings", json={"enabled": False}, headers=h)).json() == {"enabled": False}
    assert (await client.get("/api/memory/settings", headers=h)).json() == {"enabled": False}
    await _seed(client)
    listed = (await client.get("/api/memory", headers=h)).json()
    assert [m["memory_text"] for m in listed] == ["Prefers concise answers"]


async def test_memory_edit_delete_clear_and_isolation(client):
    a = await register_and_login(client, "a@example.com")
    b = await register_and_login(client, "b@example.com")
    await _seed(client)
    mid = (await client.get("/api/memory", headers=a)).json()[0]["id"]
    assert (await client.get("/api/memory", headers=b)).json() == []
    assert (await client.patch(f"/api/memory/{mid}", json={"memory_text": "hacked"}, headers=b)).status_code == 404
    assert (await client.delete(f"/api/memory/{mid}", headers=b)).status_code == 404
    assert (await client.patch(f"/api/memory/{mid}", json={"memory_text": " updated "}, headers=a)).json()["memory_text"] == "updated"
    assert (await client.delete("/api/memory", headers=a)).json() == {"deleted": True}
    assert (await client.get("/api/memory", headers=a)).json() == []


async def test_memory_requires_auth(client):
    assert (await client.get("/api/memory")).status_code == 401
    assert (await client.delete("/api/memory")).status_code == 401
