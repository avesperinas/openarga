from __future__ import annotations

WRITE = {"x-arga-scopes": "__MODULE_ID__:write"}
READ = {"x-arga-scopes": "__MODULE_ID__:read"}


async def test_a_reading_written_with_a_tool_is_read_with_another(api) -> None:
    added = await api.post(
        "/tools/add_reading", json={"label": "sueño", "value": 7.5}, headers=WRITE
    )
    assert added.status_code == 200, added.text
    await api.post("/tools/set_target", json={"label": "sueño", "value": 8}, headers=WRITE)

    read = (await api.post("/tools/get_readings", json={}, headers=READ)).json()["content"]

    assert [one["label"] for one in read["readings"]] == ["sueño"]
    assert read["targets"] == {"sueño": 8.0}


async def test_a_write_tool_with_a_read_scope_is_stopped_by_postgres(api) -> None:
    response = await api.post(
        "/tools/set_target", json={"label": "peso", "value": 70}, headers=READ
    )

    assert response.status_code == 403
    assert "Postgres" in response.json()["detail"]


async def test_the_tools_say_the_shape_of_their_arguments(api) -> None:
    shapes = {tool["name"]: tool["input_schema"] for tool in (await api.get("/tools")).json()}

    assert set(shapes) == {"get_readings", "add_reading", "set_target"}
    assert shapes["add_reading"]["required"] == ["label", "value"]
