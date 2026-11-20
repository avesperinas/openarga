from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona, localizer
from notebook import notes

say = localizer(Path(__file__).parent / "seed" / "i18n")

REVIEW = "next_review"
JOURNAL = "Journal"


def _say_note(persona: Persona, content: str) -> str:
    if not content.startswith("---\n"):
        return say(persona, content)
    end = content.index("---\n", 4) + 4
    return content[:end] + say(persona, content[end:])


def _review(day: date, tags: str) -> str:
    return f"---\n{REVIEW}: {day.isoformat()}\ntags: [{tags}]\n---\n"


def _notes(persona: Persona, today: date) -> list[tuple[str, str, str]]:
    soon, late = today + timedelta(days=3), today - timedelta(days=2)
    week, month = today + timedelta(days=9), today + timedelta(days=24)
    if persona.key == "alex":
        return [
            (
                "",
                "Home",
                "Start here.\n\n- [[Ideas]]\n- [[Reading list]]\n- [[Quantum map]]\n"
                "- [[German map]]\n- [[Travel log]]\n- [[Weekly review]]\n",
            ),
            (
                "",
                "Ideas",
                "- Learn to bake bread\n- A weekend in the mountains\n"
                "- Build a tiny data dashboard for [[Running plan 10k]]\n- [[Reading list]]\n",
            ),
            (
                "",
                "Reading list",
                "Books to look for, see [[Ideas]].\n\n- The Winter Observatory (in progress)\n"
                "- The Ninth Meridian\n- A Brief History of Salt\n",
            ),
            (
                "",
                "Weekly review",
                "Every Sunday:\n\n1. What did I finish?\n2. What slipped? See [[Goals]].\n"
                "3. Next week's three priorities.\n",
            ),
            (
                "",
                "Goals",
                "- Run a 10k under 55 minutes ([[Running plan 10k]])\n"
                "- Read 24 books this year ([[Reading list]])\n"
                "- B1 German by spring ([[German map]])\n",
            ),
            (
                "Study/German",
                "German map",
                "Notes: [[Dative prepositions]], [[Accusative prepositions]], "
                "[[Verb position]], [[Travel vocabulary]].\n",
            ),
            (
                "Study/German",
                "Dative prepositions",
                _review(late, "german")
                + "# Dative prepositions\n\naus, bei, mit, nach, seit, von, zu.\n\n"
                "See [[Accusative prepositions]].\n",
            ),
            (
                "Study/German",
                "Accusative prepositions",
                _review(soon, "german")
                + "# Accusative prepositions\n\ndurch, für, gegen, ohne, um.\n\n"
                "See [[Dative prepositions]].\n",
            ),
            (
                "Study/German",
                "Verb position",
                _review(week, "german")
                + "# Verb position\n\nMain clause: verb second. Subordinate: verb last.\n"
                "Example: Ich weiß, dass er morgen kommt.\n",
            ),
            (
                "Study/German",
                "Travel vocabulary",
                "der Bahnhof, die Fahrkarte, das Gleis, die Verspätung.\n"
                "Used on the [[Travel log]] trips.\n",
            ),
            (
                "Study/Quantum",
                "Quantum map",
                "- [[Qubits and the Bloch sphere]]\n- [[Entanglement and Bell states]]\n"
                "- [[Quantum gates cheat sheet]]\n- [[Grover search]]\n",
            ),
            (
                "Study/Quantum",
                "Qubits and the Bloch sphere",
                _review(today, "quantum")
                + "# Qubits and the Bloch sphere\n\nA qubit is a unit vector on the sphere. "
                "Gates are rotations: see [[Quantum gates cheat sheet]].\n",
            ),
            (
                "Study/Quantum",
                "Entanglement and Bell states",
                _review(week, "quantum") + "# Entanglement\n\n|Φ+> = (|00> + |11>)/√2.\n"
                "Measuring one qubit fixes the other.\n"
                "Back to [[Quantum map]].\n",
            ),
            (
                "Study/Quantum",
                "Quantum gates cheat sheet",
                "H, X, Y, Z, CNOT, T.\n\n"
                "CNOT after H makes a Bell pair ([[Entanglement and Bell states]]).\n",
            ),
            (
                "Study/Quantum",
                "Grover search",
                _review(month, "quantum")
                + "# Grover\n\nQuadratic speed-up: about √N oracle calls.\n",
            ),
            (
                "Work",
                "Postgres row level security",
                "Policies per table, one role per app.\n\n"
                "Checklist: enable, force, test with another user.\n"
                "See [[Data pipeline checklist]].\n",
            ),
            (
                "Work",
                "Data pipeline checklist",
                "- Idempotent loads\n- Backfill plan\n- Alerts on freshness\n"
                "- Document the contract\n",
            ),
            (
                "Work",
                "Migration week retro",
                "Went well: small steps. Slipped: the backfill took two days.\n"
                "Action: dry run first. Related: [[Data pipeline checklist]].\n",
            ),
            (
                "Projects/Home",
                "Kitchen shelves",
                "- Measure the wall\n- Buy brackets\n- Ask Sam about the colour\n",
            ),
            (
                "Projects/Home",
                "Balcony plan",
                "Herbs: basil, mint, rosemary. Shared with [[Kitchen shelves]] errands.\n",
            ),
            (
                "Travel",
                "Travel log",
                "- [[Flanders in September]]\n- [[Copenhagen packing]]\n"
                "- Next: Lisbon, Dolomites.\n",
            ),
            (
                "Travel",
                "Flanders in September",
                "Bruges belfry before ten. Ghent at night was the best part. "
                "Waffles: Bruges beats Ghent.\n",
            ),
            (
                "Travel",
                "Copenhagen packing",
                "Passport, warm layers, camera, adapter. Back to [[Travel log]].\n",
            ),
            (
                "Health",
                "Running plan 10k",
                "Tue easy 5k, Sat long run, Padel as cross-training. "
                "Target pace 5:30. See [[Goals]].\n",
            ),
            (
                "Health",
                "Blood test notes",
                "LDL trending down since the diet change. Retest in spring.\n",
            ),
        ]
    return [
        (
            "",
            "Home",
            "Start here.\n\n- [[Ideas]]\n- [[Garden plan]]\n- [[Book club]]\n- [[Trips]]\n",
        ),
        (
            "",
            "Ideas",
            "- Try a new pasta shape\n- [[Garden plan]]\n- Pottery pieces for [[Gifts]]\n",
        ),
        (
            "",
            "Gifts",
            "- Alex: climbing shoes\n- Marta: ceramic bowl ([[Pottery class]])\n- Mum: orchids\n",
        ),
        (
            "Projects",
            "Garden plan",
            _review(late, "garden") + "# Garden plan\n\nTomatoes, basil and beans.\n",
        ),
        ("Projects", "Bike repair", "Chain, brakes and the back light. See [[Ideas]].\n"),
        (
            "Projects",
            "Pottery class",
            _review(soon, "pottery")
            + "# Pottery class\n\nWeek 3: centring the clay. Week 4: handles.\nFor [[Gifts]].\n",
        ),
        (
            "Book club",
            "Book club",
            "First Thursday of the month.\n\n- [[La casa de los cipreses]]\n"
            "- [[El peso de la sal]]\n",
        ),
        ("Book club", "La casa de los cipreses", "Loved the grandmother chapters. Rated 4.5.\n"),
        ("Book club", "El peso de la sal", "Tight ending. Ask the group about the last chapter.\n"),
        (
            "Trips",
            "Trips",
            "- [[Paris for Marta]]\n- [[Marrakech tips]]\n- [[Tenerife]]\n- Next: Prague.\n",
        ),
        (
            "Trips",
            "Paris for Marta",
            "The cake surprise worked. Versailles fountains show is Saturday only.\n",
        ),
        (
            "Trips",
            "Marrakech tips",
            "Haggle with a smile. Hammam on the second day. Essaouira is windy.\n",
        ),
        (
            "Trips",
            "Tenerife",
            "Sunrise at Teide: book the cable car early. Papas arrugadas everywhere.\n",
        ),
        (
            "Health",
            "Pilates routine",
            _review(week, "health")
            + "# Pilates\n\nMon and Wed, 55 minutes. Focus: core and hips.\n",
        ),
        ("Health", "Swimming log", "Thursdays 7:30. 40 minutes. Breathing every three strokes.\n"),
        (
            "Work",
            "Data tools training",
            "Notes from the training day: dbt basics, tests and docs.\nFollow-up: [[Ideas]].\n",
        ),
        (
            "Money",
            "Budget rules",
            "Fixed costs first, savings on payday, no impulse buys over 50 euros "
            "without sleeping on it.\n",
        ),
        ("Poetry", "Favourite verses", "Collected lines. Reread on rainy Sundays.\n"),
    ]


def _days(persona: Persona, today: date) -> list[tuple[date, str]]:
    if persona.key == "alex":
        lines = [
            "Long walk after work.",
            "Read for an hour: [[Reading list]].",
            "Called the family.",
            "Quantum lecture: reviewed [[Qubits and the Bloch sphere]].",
            "German practice, ten minutes: [[Dative prepositions]].",
            "Easy run, felt great: [[Running plan 10k]].",
            "Cooked curry for Sam.",
            "Padel with the team.",
            "Fixed a flaky pipeline, see [[Data pipeline checklist]].",
        ]
    else:
        lines = [
            "Swimming in the morning.",
            "Cooked for friends.",
            "Quiet day at home.",
            "Pottery class, wobbly bowl: [[Pottery class]].",
            "Pilates, sore core: [[Pilates routine]].",
            "Read in the park.",
            "Book club night: [[Book club]].",
            "Weeded the garden: [[Garden plan]].",
            "Lunch at the parents'.",
        ]
    return [
        (today - timedelta(days=n), f"- {say(persona, lines[n % len(lines)])}\n")
        for n in range(0, 45)
    ]


async def _create(connection: AsyncConnection, folder: str, title: str, content: str) -> None:
    try:
        await notes.create(connection, folder, title, content)
    except notes.Conflict:
        return


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    await notes.save_settings(
        connection, notes.Settings(daily_folder=say(persona, JOURNAL), review_property=REVIEW)
    )
    for folder, title, content in _notes(persona, today):
        await _create(
            connection, say(persona, folder), say(persona, title), _say_note(persona, content)
        )
    for day, content in _days(persona, today):
        await _create(connection, say(persona, JOURNAL), day.isoformat(), content)
