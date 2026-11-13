from __future__ import annotations

import pytest

from vitals import labs

PDF = b"%PDF-1.4\n% a made-up check-up\n%%EOF\n"


async def checkup(api, day: str, center: str = "Test lab") -> str:
    response = await api.post("/checkups", json={"day": day, "center": center})
    assert response.status_code == 201
    return response.json()["id"]


async def result(api, checkup_id: str, **body):
    return await api.post(f"/checkups/{checkup_id}/results", json=body)


def test_units_are_read_however_a_report_writes_them() -> None:
    assert labs.unit_key("x10^3/uL") == labs.unit_key("10³/µL") == labs.unit_key("10^3/µL")
    assert labs.unit_key("mill / µL") == labs.unit_key("10^6/µL")
    assert labs.unit_key("mg/dl") == labs.unit_key("mg/dL")
    assert labs.unit_key("U/I") == labs.unit_key("UI/l") == labs.unit_key("U/L")
    assert labs.unit_key("·10³/µl") == labs.unit_key("x 10^3/uL") == labs.unit_key("10^3/µL")


def test_names_are_matched_without_accents_or_the_asterisk() -> None:
    assert labs.plain(" Colesterol  LDL* ") == "colesterol ldl"
    assert labs.plain("\u00c1CIDO \u00daRICO") == "acido urico"


@pytest.mark.parametrize(
    ("value", "low", "high", "out"),
    [(151, 0, 130, True), (120, None, 130, False), (38, 40, None, True), (5, None, None, False)],
)
def test_out_of_range_is_against_the_reports_own_range(value, low, high, out) -> None:
    assert labs.out_of_range(value, low, high) is out


async def test_the_catalogue_comes_seeded_in_reading_order(api) -> None:
    analytes = (await api.get("/analytes")).json()

    ids = [one["id"] for one in analytes]
    assert ids[:2] == ["rbc", "hemoglobin"]
    assert {"ldl", "hdl", "cholesterol", "triglycerides", "glucose", "urine_ph"} <= set(ids)
    assert all(one["about"] for one in analytes)


async def test_the_same_checkup_twice_is_one(api) -> None:
    first = await api.post("/checkups", json={"day": "2026-09-02", "center": "Occupational health"})
    again = await api.post("/checkups", json={"day": "2026-09-02", "center": "Occupational health"})

    assert first.json() == {"id": first.json()["id"], "existed": False}
    assert again.json() == {"id": first.json()["id"], "existed": True}


async def test_a_value_is_found_by_the_name_the_report_uses(api) -> None:
    found = await checkup(api, "2026-09-02")

    added = await result(
        api, found, analyte="LDL COLESTEROL", value=151, unit="mg/dl", ref_low=0, ref_high=130
    )

    assert added.status_code == 201
    assert added.json()["analyte"] == "ldl"
    assert added.json()["out"] is True


async def test_an_unknown_analyte_says_which_ones_there_are(api) -> None:
    found = await checkup(api, "2026-09-02")

    response = await result(api, found, analyte="unobtainium", value=1)

    assert response.status_code == 404
    assert "ldl" in response.json()["detail"]


async def test_the_same_analyte_again_corrects_it(api) -> None:
    found = await checkup(api, "2026-09-02")
    await result(api, found, analyte="glucose", value=87, unit="mg/dL", ref_low=60, ref_high=110)

    again = await result(
        api, found, analyte="glucose", value=78, unit="mg/dL", ref_low=60, ref_high=110
    )

    assert again.json()["replaced"] is True
    table = (await api.get("/labs")).json()
    assert table["rows"][0]["cells"][found]["value"] == 78


async def test_the_table_marks_what_is_out_and_counts_it_per_checkup(api) -> None:
    older = await checkup(api, "2025-06-11")
    newer = await checkup(api, "2026-09-02")
    await result(api, older, analyte="ldl", value=118, unit="mg/dL", ref_high=130)
    await result(api, newer, analyte="ldl", value=151, unit="mg/dL", ref_high=130)
    await result(api, newer, analyte="urine_protein", value_text="Negativo")

    table = (await api.get("/labs")).json()

    assert [one["day"] for one in table["checkups"]] == ["2026-09-02", "2025-06-11"]
    assert [one["out"] for one in table["checkups"]] == [1, 0]
    rows = {row["analyte"]["id"]: row["cells"] for row in table["rows"]}
    assert rows["ldl"][newer]["out"] is True
    assert rows["ldl"][older]["out"] is False
    assert rows["urine_protein"][newer]["value_text"] == "Negativo"


async def test_the_evolution_is_in_the_canonical_unit(api) -> None:
    first = await checkup(api, "2024-10-01")
    second = await checkup(api, "2026-05-11")
    await result(api, first, analyte="ldl", value=3.1, unit="mmol/L", ref_high=3.36)
    await result(api, second, analyte="ldl", value=133, unit="mg/dL", ref_high=130)
    third = await checkup(api, "2026-09-02")
    await result(api, third, analyte="ldl", value=5, unit="unidad rara")

    found = (await api.get("/labs/ldl")).json()

    assert [(one["day"], one["value"]) for one in found["points"]] == [
        ("2024-10-01", 119.877),
        ("2026-05-11", 133.0),
    ]
    assert found["points"][0]["ref_high"] == pytest.approx(129.93, abs=0.01)
    assert found["skipped"] == 1


async def test_a_pdf_is_kept_and_served_back(api) -> None:
    found = await checkup(api, "2026-09-02")

    saved = await api.put(
        f"/checkups/{found}/document", params={"filename": "checkup.pdf"}, content=PDF
    )
    served = await api.get(f"/checkups/{found}/document")

    assert saved.status_code == 204
    assert served.content == PDF
    assert served.headers["content-type"] == "application/pdf"
    assert (await api.get("/checkups")).json()[0]["document"] == "checkup.pdf"


async def test_what_is_not_a_pdf_is_refused(api) -> None:
    found = await checkup(api, "2026-09-02")

    response = await api.put(f"/checkups/{found}/document", content=b"<html>no</html>")

    assert response.status_code == 409


async def test_a_value_without_number_or_text_is_a_422(api) -> None:
    found = await checkup(api, "2026-09-02")

    assert (await result(api, found, analyte="ldl")).status_code == 422
