from __future__ import annotations

WRITE = {"x-arga-scopes": "vitals:write"}
READ = {"x-arga-scopes": "vitals:read"}


async def test_a_weighing_from_claude_is_in_the_line_with_its_source(api) -> None:
    response = await api.post(
        "/tools/log_weight", json={"kg": 80.2, "date": "2026-09-10"}, headers=WRITE
    )

    assert response.status_code == 200
    content = response.json()["content"]
    assert content["logged"] == {"date": "2026-09-10", "kg": 80.2, "already_there": False}
    assert content["latest_average_7d"] == 80.2
    found = (await api.get("/weight")).json()
    assert [one["source"] for one in found["entries"]] == ["claude"]


async def test_loading_a_history_twice_repeats_nothing(api) -> None:
    history = [("2026-01-05", 84.1), ("2026-01-12", 83.6), ("2026-01-19", 83.0)]
    for day, kg in history * 2:
        await api.post(
            "/tools/log_weight", json={"kg": kg, "date": day, "from_history": True}, headers=WRITE
        )

    found = (await api.get("/weight")).json()

    assert len(found["entries"]) == 3
    assert {one["source"] for one in found["entries"]} == {"history"}


async def test_with_only_read_postgres_refuses_to_log(api) -> None:
    response = await api.post("/tools/log_weight", json={"kg": 80}, headers=READ)

    assert response.status_code == 403
    assert (await api.get("/weight")).json()["entries"] == []


async def test_bad_arguments_are_a_422(api) -> None:
    response = await api.post("/tools/log_weight", json={"kg": "mucho"}, headers=WRITE)

    assert response.status_code == 422


async def test_the_arguments_are_described_for_the_model(api) -> None:
    listed = (await api.get("/tools")).json()

    shape = next(one for one in listed if one["name"] == "log_weight")["input_schema"]
    assert set(shape["properties"]) == {"kg", "date", "time", "note", "from_history"}
    assert {one["name"] for one in listed} == {
        "get_kpis",
        "get_steps",
        "get_weight",
        "get_body",
        "get_sleep",
        "get_heart_day",
        "get_heart_rhythm",
        "get_today",
        "get_stress",
        "get_workouts",
        "get_training_load",
        "get_sleep_patterns",
        "get_checkup_changes",
        "get_band",
        "get_lab_results",
        "get_checkups",
        "log_weight",
        "record_checkup",
        "add_lab_result",
    }
    assert shape["required"] == ["kg"]


async def test_claude_loads_a_checkup_and_reads_it_back(api) -> None:
    created = await api.post(
        "/tools/record_checkup",
        json={"date": "2026-09-02", "center": "Test occupational health"},
        headers=WRITE,
    )
    checkup_id = created.json()["content"]["checkup_id"]
    for body in (
        {"analyte": "Colesterol LDL", "value": 151, "unit": "mg/dL", "ref_low": 0, "ref_high": 130},
        {"analyte": "HDL COLESTEROL", "value": 79, "unit": "mg/dL", "ref_low": 40, "ref_high": 200},
        {"analyte": "unobtainium", "value": 1},
    ):
        await api.post(
            "/tools/add_lab_result", json={"checkup_id": checkup_id, **body}, headers=WRITE
        )

    read = (
        await api.post("/tools/get_lab_results", json={"analytes": ["ldl"]}, headers=READ)
    ).json()["content"]
    checkups = (await api.post("/tools/get_checkups", json={}, headers=READ)).json()["content"]

    assert read["results"][0]["values"][0]["value"] == 151
    assert read["results"][0]["values"][0]["out"] is True
    assert checkups["checkups"][0]["values"] == 2
    assert checkups["checkups"][0]["out_of_range"] == 1


async def test_an_unknown_analyte_is_said_not_written(api) -> None:
    created = await api.post("/tools/record_checkup", json={"date": "2026-09-02"}, headers=WRITE)
    checkup_id = created.json()["content"]["checkup_id"]

    added = await api.post(
        "/tools/add_lab_result",
        json={"checkup_id": checkup_id, "analyte": "unobtainium", "value": 1},
        headers=WRITE,
    )

    assert added.json()["content"]["added"] is None
    assert "ldl" in added.json()["content"]["note"]


async def test_the_kpis_answer_how_am_i_doing(api) -> None:
    await api.put("/goals", json={"steps_per_day": 8000, "weight_max_kg": 76})
    await api.post("/tools/log_weight", json={"kg": 78.4}, headers=WRITE)
    first = await api.post("/tools/record_checkup", json={"date": "2025-06-11"}, headers=WRITE)
    second = await api.post("/tools/record_checkup", json={"date": "2026-09-02"}, headers=WRITE)
    for created, value in ((first, 118), (second, 151)):
        await api.post(
            "/tools/add_lab_result",
            json={
                "checkup_id": created.json()["content"]["checkup_id"],
                "analyte": "ldl",
                "value": value,
                "unit": "mg/dL",
                "ref_high": 130,
            },
            headers=WRITE,
        )

    kpis = (await api.post("/tools/get_kpis", json={}, headers=READ)).json()["content"]

    assert kpis["weight"]["average_7"] == 78.4
    assert kpis["weight"]["against_goal"] == "above"
    assert kpis["ldl"]["value"] == 151
    assert kpis["ldl"]["previous"] == 118
    assert kpis["ldl"]["out"] is True
    assert kpis["steps"]["goal"] == 8000


async def test_steps_and_weight_read_with_the_read_scope(api) -> None:
    await api.post("/tools/log_weight", json={"kg": 80, "date": "2026-09-01"}, headers=WRITE)

    weight = await api.post("/tools/get_weight", json={"since": "2026-01-01"}, headers=READ)
    steps = await api.post("/tools/get_steps", json={"group_by": "month"}, headers=READ)

    assert weight.json()["content"]["days"][0]["kg"] == 80
    assert steps.json()["content"]["items"] == []
    assert steps.json()["content"]["mean_per_day"] is None


async def test_the_body_reads_with_the_read_scope_and_names_what_it_does_not_know(api) -> None:
    empty = await api.post("/tools/get_body", json={}, headers=READ)
    unknown = await api.post("/tools/get_body", json={"metrics": ["libido"]}, headers=READ)
    one = await api.post(
        "/tools/get_body", json={"metrics": ["hrv_ms"], "group_by": "month"}, headers=READ
    )

    assert empty.json()["content"]["profile"] is None
    assert unknown.json()["content"]["unknown"] == ["libido"]
    assert "resting_heart_rate" in unknown.json()["content"]["known"]
    assert one.json()["content"]["metrics"]["hrv_ms"]["points"] == []
