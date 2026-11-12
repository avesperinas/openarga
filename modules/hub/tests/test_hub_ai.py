from hub import ai
from hub.capabilities import CAPABILITIES


async def test_extract_answers_with_the_shape_asked_for() -> None:
    answer = await ai.extract(
        "outings",
        {
            "instructions": "List the events on the page.",
            "input": "Jazz night on Friday.",
            "output_schema": {
                "type": "object",
                "properties": {"events": {"type": "array"}, "page": {"type": "string"}},
            },
        },
    )

    assert answer["output"] == {"events": [], "page": ""}
    assert answer["provider"] == "fake"


async def test_run_is_idempotent_by_key_and_says_who_ran_it() -> None:
    first = await ai.run("insights", {"task": "Look at the week.", "key": "week-46"})
    again = await ai.run("insights", {"task": "Look at the week.", "key": "week-46"})

    assert first["run_id"] == again["run_id"]
    assert first["status"] == "done" and first["provider"] == "fake"


def test_both_are_capabilities_of_the_hub() -> None:
    assert {"ai.extract", "ai.run"} <= set(CAPABILITIES)
