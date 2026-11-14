from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from insights import insights, tastes
from insights.insights import Figure, InsightIn, Proposal

ABOUT = {
    "alex": "I work in an office, run twice a week and I am learning German.",
    "sam": "I swim in the mornings, cook for friends and save for a long trip.",
}

TRAITS = {
    "alex": [
        ("topic", "Ancient history", 2),
        ("genre", "Historical novels", 1),
        ("avoid", "Football", -2),
    ],
    "sam": [("topic", "Oceans", 2), ("format", "Podcasts", 1), ("topic", "Food science", 1)],
}


def _alert(persona: Persona) -> InsightIn:
    if persona.key == "alex":
        return InsightIn(
            domain="body",
            topic="vitals.sleep",
            title="Your sleep is an hour short this week",
            body=(
                "You slept 6.2 hours a night this week, against 7.1 in your last three months.\n\n"
                "The two nights after a late run were the shortest."
            ),
            figures=[
                Figure(
                    label="sleep",
                    value=6.2,
                    unit="h",
                    baseline=7.1,
                    baseline_label="your 90-day average",
                )
            ],
            affects="the half marathon goal",
            action="Move Thursday's run to the morning and be in bed by 23:00 four nights.",
        )
    return InsightIn(
        domain="money",
        topic="money.spend:restaurants",
        title="Restaurants are a third above your usual",
        body=(
            "You spent 186 € in restaurants this month, against 140 € in a usual month.\n\n"
            "At this pace the trip fund gets 46 € less."
        ),
        figures=[
            Figure(
                label="restaurants this month",
                value=186,
                unit="€",
                baseline=140,
                baseline_label="your monthly average",
            )
        ],
        affects="the trip fund",
        action="Cook at home three dinners from Monday to Thursday next week.",
    )


def _weekly(persona: Persona, sunday: date) -> InsightIn:
    steps = Figure(
        label="steps a day", value=7400, unit="steps", baseline=8000, baseline_label="your target"
    )
    return InsightIn(
        kind="weekly",
        domain="cross",
        topic=f"week:{sunday.isocalendar()[0]}-w{sunday.isocalendar()[1]:02d}",
        title="A steady week, a little short on steps",
        body=(
            "Money stayed within its pace and the goals moved forward.\n\n"
            "Steps were below your target on four days."
        ),
        figures=[steps],
        affects="the daily steps goal",
        action="Walk to work on Tuesday and Thursday, and keep the rest as it is.",
        proposals=[
            Proposal(
                what="Walk to work on Tuesday and Thursday",
                figure=steps,
                how="Planner: two 30 min blocks at 8:00",
            ),
            Proposal(
                what="Three dinners at home from Monday to Thursday",
                figure=steps,
                how="Shopping: add three dinners to the list",
            ),
            Proposal(
                what="One long walk on Saturday morning",
                figure=steps,
                how="Planner: a 90 min block on Saturday at 10:00",
            ),
        ],
    )


def _pills(persona: Persona) -> list[dict[str, Any]]:
    if persona.key == "alex":
        return [
            {
                "family_key": "history",
                "topic": "The oblique order at Leuctra",
                "headline": "The column that broke Sparta",
                "lead": (
                    "In 371 BC a Theban general beat an army that had not lost a pitched battle "
                    "in centuries."
                ),
                "sections": [
                    (
                        "A deeper left wing",
                        (
                            "Epaminondas stacked his left wing fifty men deep, where custom put "
                            "the best troops on the right, and held his weak wing back."
                        ),
                    ),
                    (
                        "Why it worked",
                        (
                            "The Spartan king stood on the right, facing the deep column; when it"
                            " broke through, the rest of the Spartan line lost its head and its "
                            "nerve."
                        ),
                    ),
                ],
                "to_tell": "At Leuctra the Thebans won by making their left wing fifty ranks deep.",
                "source": ("Battle of Leuctra", "https://en.wikipedia.org/wiki/Battle_of_Leuctra"),
            },
            {
                "family_key": "science",
                "topic": "Why the sky is blue",
                "headline": "A sky coloured by small molecules",
                "lead": (
                    "Air scatters short wavelengths far more than long ones, and that is the "
                    "whole trick."
                ),
                "sections": [
                    (
                        "Rayleigh scattering",
                        (
                            "Molecules much smaller than the wavelength scatter light with a "
                            "strength that grows as the fourth power of its frequency."
                        ),
                    ),
                    (
                        "And sunsets",
                        (
                            "At sunset light crosses much more air, the blue is scattered away on"
                            " the way and the reds and oranges are what reaches you."
                        ),
                    ),
                ],
                "to_tell": (
                    "Blue light is scattered about five times more than red light by the air."
                ),
                "source": (
                    "Rayleigh scattering",
                    "https://en.wikipedia.org/wiki/Rayleigh_scattering",
                ),
            },
        ]
    return [
        {
            "family_key": "nature",
            "topic": "How octopuses taste with their arms",
            "headline": "An animal that tastes what it touches",
            "lead": (
                "Most of an octopus's neurons are in its arms, and their suckers carry taste "
                "receptors."
            ),
            "sections": [
                (
                    "Arms that decide",
                    (
                        "Each arm can explore, grab and reject food on its own, sending only a "
                        "summary of what it found to the brain."
                    ),
                ),
                (
                    "Taste by touch",
                    (
                        "The suckers carry receptors that detect chemicals on surfaces, so "
                        "touching a rock is also tasting it."
                    ),
                ),
            ],
            "to_tell": "Two thirds of an octopus's neurons are in its arms, not in its head.",
            "source": ("Octopus", "https://en.wikipedia.org/wiki/Octopus"),
        },
        {
            "family_key": "science",
            "topic": "The Maillard reaction",
            "headline": "Why browned food tastes better",
            "lead": (
                "Above about 140 degrees, sugars and amino acids react and make hundreds of new "
                "flavours."
            ),
            "sections": [
                (
                    "Not caramel",
                    (
                        "Caramelisation is sugar alone; the Maillard reaction needs proteins too,"
                        " which is why bread crust and seared meat taste different."
                    ),
                ),
                (
                    "Dry heat",
                    (
                        "Water keeps food at 100 degrees, so the surface has to dry before it "
                        "browns: that is why a crowded pan steams instead."
                    ),
                ),
            ],
            "to_tell": (
                "Food only browns once its surface dries, because water caps it at 100 degrees."
            ),
            "source": ("Maillard reaction", "https://en.wikipedia.org/wiki/Maillard_reaction"),
        },
    ]


async def _publish(connection: AsyncConnection, insight: InsightIn, when: datetime) -> None:
    exists = await connection.scalar(
        text("select 1 from insights.insights_insight where topic = :topic"),
        {"topic": insight.topic},
    )
    if exists:
        return
    found = await insights.publish(connection, insight)
    await connection.execute(
        text(
            "update insights.insights_insight set created_at = :when where id = cast(:id as uuid)"
        ),
        {"when": when, "id": found.id},
    )


async def _pill(connection: AsyncConnection, day: date, pill: dict[str, Any], read: bool) -> None:
    exists = await connection.scalar(
        text("select 1 from insights.insights_pill where day = :day and origin = 'daily'"),
        {"day": day},
    )
    if exists:
        return
    title, url = pill["source"]
    await connection.execute(
        text("""
            insert into insights.insights_pill
                (day, origin, family_key, topic, language, minutes, headline, lead, sections,
                 to_tell, sources, read_at)
            values (:day, 'daily', :family_key, :topic, 'en', 5, :headline, :lead,
                    cast(:sections as jsonb), :to_tell, cast(:sources as jsonb), :read_at)
        """),
        {
            "day": day,
            "family_key": pill["family_key"],
            "topic": pill["topic"],
            "headline": pill["headline"],
            "lead": pill["lead"],
            "sections": json.dumps([{"title": t, "text": body} for t, body in pill["sections"]]),
            "to_tell": pill["to_tell"],
            "sources": json.dumps([{"title": title, "url": url, "language": "en"}]),
            "read_at": datetime.combine(day, time(9, 30), UTC) if read else None,
        },
    )


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    await tastes.ensure_defaults(connection)
    await insights.save_profile(connection, insights.ProfileIn(about=ABOUT[persona.key]))
    await tastes.mark_started(connection)
    for facet, label, stance in TRAITS[persona.key]:
        await tastes.remember(connection, facet, label, stance, "said", confirmed=True)
    sunday = today - timedelta(days=today.isoweekday() % 7)
    await _publish(connection, _weekly(persona, sunday), datetime.combine(sunday, time(19), UTC))
    await _publish(connection, _alert(persona), datetime.combine(today, time(8), UTC))
    earlier, latest = _pills(persona)
    await _pill(connection, today - timedelta(days=1), earlier, read=True)
    await _pill(connection, today, latest, read=False)
