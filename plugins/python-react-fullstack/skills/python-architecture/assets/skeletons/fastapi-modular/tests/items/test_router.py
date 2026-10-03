from httpx import AsyncClient

BASE = "/api/v1/items"


async def test_create_and_list(client: AsyncClient) -> None:
    response = await client.post(BASE, json={"name": "Widget", "price": 9.5})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1

    listing = await client.get(BASE)
    assert listing.status_code == 200
    assert [item["name"] for item in listing.json()] == ["Widget"]


async def test_patch_and_delete(client: AsyncClient) -> None:
    item_id = (await client.post(BASE, json={"name": "Widget", "price": 9.5})).json()["id"]

    patched = await client.patch(f"{BASE}/{item_id}", json={"price": 20})
    assert patched.json()["price"] == 20

    assert (await client.delete(f"{BASE}/{item_id}")).status_code == 204
    assert (await client.get(f"{BASE}/{item_id}")).status_code == 404


async def test_not_found_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/42")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_validation_error(client: AsyncClient) -> None:
    response = await client.post(BASE, json={"name": "", "price": -1})
    assert response.status_code == 422
