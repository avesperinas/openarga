from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module import i18n
from arga_module.demo import Persona
from arga_tenancy import current_spaces
from goals.common import CATALOGS

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-00000060a150")
WEEKS = 78

PERSON = text("""
    insert into goals.goals_person (seeded_at, goals_seeded_at) values (now(), now())
    on conflict (user_id) do nothing
""")

CATEGORY = text("""
    insert into goals.goals_category (id, name, hue, position, space_id)
    values (:id, :name, :hue, :position, :space_id)
    on conflict (id) do nothing
""")

TASK = text("""
    insert into goals.goals_task
        (id, category_id, title, notes, due_on, due_time, rule, series_on, done_at, done_by,
         space_id, created_at)
    values (:id, :category_id, :title, :notes, :due_on, :due_time, :rule, :series_on, :done_at,
            :done_by, :space_id, :created_at)
    on conflict (id) do nothing
""")

GOAL = text("""
    insert into goals.goals_goal
        (id, category_id, title, kind, metric_key, metric_label, metric_unit, metric_kind,
         direction, target, period, days_per_week, start_value, start_on, due_on, status,
         closed_on, closed_value, note, featured, position)
    values (:id, :category_id, :title, :kind, :metric_key, :metric_label, :metric_unit,
            :metric_kind, :direction, :target, :period, :days_per_week, :start_value, :start_on,
            :due_on, :status, :closed_on, :closed_value, :note, :featured, :position)
    on conflict (id) do nothing
""")

CHECK = text("""
    insert into goals.goals_goal_check (id, goal_id, day, done, value)
    values (:id, :goal_id, :day, :done, :value)
    on conflict (goal_id, day) do nothing
""")

CATEGORIES = (
    ("work", 1),
    ("home", 2),
    ("personal", 5),
    ("health", 6),
    ("learning", 7),
)

CHORES = (
    ("work", "Send the weekly report"),
    ("work", "Review the open pull requests"),
    ("home", "Water the plants"),
    ("home", "Clean the kitchen"),
    ("personal", "Call the family"),
    ("personal", "Pay the gym membership"),
    ("health", "Stretch for ten minutes"),
    ("learning", "Read one chapter"),
)


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.key}:{key}")


def _name(persona: Persona, key: str) -> str:
    return i18n.t(CATALOGS, f"category.{key}", persona.locale)


def _task(persona: Persona, key: str, category: UUID, title: str, **fields) -> dict:
    return {
        "id": _id(persona, f"task-{key}"),
        "category_id": category,
        "title": title,
        "notes": None,
        "due_on": None,
        "due_time": None,
        "rule": None,
        "series_on": None,
        "done_at": None,
        "done_by": None,
        "space_id": None,
        "created_at": datetime.now(UTC),
        **fields,
    }


def _done(persona: Persona, categories: dict[str, UUID], today: date, zone: ZoneInfo) -> list:
    found = []
    shift = 0 if persona.key == "alex" else 3
    for week in range(1, WEEKS + 1):
        for slot in range(3):
            index = week * 3 + slot + shift
            category, title = CHORES[index % len(CHORES)]
            day = today - timedelta(days=week * 7 - slot * 2)
            done_at = datetime.combine(day, time(18 + slot, 15), zone)
            found.append(
                _task(
                    persona,
                    f"done-{week}-{slot}",
                    categories[category],
                    title,
                    due_on=day,
                    done_at=done_at,
                    done_by=persona.id,
                    created_at=done_at - timedelta(days=2),
                )
            )
    return found


def _pending(persona: Persona, categories: dict[str, UUID], today: date) -> list:
    alex = persona.key == "alex"
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    return [
        _task(
            persona,
            "today",
            categories["work"],
            "Prepare the planning meeting" if alex else "Answer the supplier",
            due_on=today,
            due_time=time(17),
        ),
        _task(
            persona,
            "overdue",
            categories["personal"],
            "Renew the passport" if alex else "Book the car service",
            due_on=today - timedelta(days=2),
        ),
        _task(
            persona, "tomorrow", categories["home"], "Buy light bulbs", due_on=today + timedelta(1)
        ),
        _task(
            persona,
            "weekly",
            categories["home"],
            "Take the bins out",
            due_on=monday,
            rule="FREQ=WEEKLY;BYDAY=MO",
            series_on=monday,
        ),
        _task(
            persona,
            "later",
            categories["learning"],
            "Sign up for the German course" if alex else "Finish the online course",
            due_on=today + timedelta(days=24),
        ),
        _task(persona, "someday", categories["personal"], "Sort the old photos"),
    ]


def _shared(persona: Persona, category: UUID, space: UUID, today: date) -> list:
    return [
        _task(
            persona,
            "shared-plumber",
            category,
            "Call the plumber",
            due_on=today + timedelta(days=1),
            space_id=space,
        ),
        _task(
            persona,
            "shared-groceries",
            category,
            "Plan the weekly menu",
            due_on=today,
            space_id=space,
        ),
    ]


def _goal(persona: Persona, key: str, **fields) -> dict:
    return {
        "id": _id(persona, f"goal-{key}"),
        "category_id": None,
        "metric_key": None,
        "metric_label": None,
        "metric_unit": None,
        "metric_kind": None,
        "direction": "at_least",
        "target": None,
        "period": None,
        "days_per_week": None,
        "start_value": None,
        "due_on": None,
        "status": "active",
        "closed_on": None,
        "closed_value": None,
        "note": None,
        "featured": False,
        **fields,
    }


def _goals(persona: Persona, categories: dict[str, UUID], today: date) -> list[dict]:
    alex = persona.key == "alex"
    year_ago = today - timedelta(days=365)
    return [
        _goal(
            persona,
            "reading",
            category_id=categories["learning"],
            title="Read 20 minutes",
            kind="periodic",
            period="day",
            days_per_week=5,
            start_on=today - timedelta(days=WEEKS * 7),
            featured=True,
            position=1,
        ),
        _goal(
            persona,
            "steps",
            category_id=categories["health"],
            title="8,000 steps",
            kind="periodic",
            metric_key="vitals.steps",
            metric_label="Steps",
            metric_unit="steps",
            metric_kind="amount",
            target=8000,
            period="day",
            days_per_week=7,
            start_on=today - timedelta(days=120),
            position=2,
        ),
        _goal(
            persona,
            "running",
            category_id=categories["health"],
            title="Run 20 km a week" if alex else "Swim 3 km a week",
            kind="periodic",
            target=20 if alex else 3,
            period="week",
            start_on=today - timedelta(days=200),
            position=3,
        ),
        _goal(
            persona,
            "savings",
            category_id=categories["personal"],
            title="Save for the summer trip",
            kind="dated",
            target=3000,
            start_value=0,
            start_on=today - timedelta(days=90),
            due_on=today + timedelta(days=150),
            position=4,
        ),
        _goal(
            persona,
            "certificate",
            category_id=categories["learning"],
            title="Pass the B2 exam" if alex else "Get the first-aid certificate",
            kind="dated",
            start_on=today - timedelta(days=60),
            due_on=today + timedelta(days=200),
            position=5,
        ),
        _goal(
            persona,
            "half",
            category_id=categories["health"],
            title="Finish a half marathon" if alex else "Swim 1 km without stopping",
            kind="dated",
            start_on=year_ago - timedelta(days=120),
            due_on=year_ago + timedelta(days=30),
            status="achieved",
            closed_on=year_ago + timedelta(days=21),
            position=6,
        ),
        _goal(
            persona,
            "books",
            category_id=categories["learning"],
            title="Read 12 books in a year",
            kind="dated",
            target=12,
            start_value=0,
            start_on=today - timedelta(days=500),
            due_on=today - timedelta(days=135),
            status="missed",
            closed_on=today - timedelta(days=135),
            closed_value=9,
            position=7,
        ),
    ]


def _checks(persona: Persona, today: date) -> list[dict]:
    found = []
    shift = 0 if persona.key == "alex" else 2
    goal = _id(persona, "goal-reading")
    for back in range(1, WEEKS * 7):
        day = today - timedelta(days=back)
        if (back + shift) % 7 in (2, 5) or (back + shift) % 23 == 0:
            continue
        found.append(
            {"id": _id(persona, f"check-reading-{back}"), "goal_id": goal, "day": day, "done": True}
        )
    weekly = _id(persona, "goal-running")
    for back in range(1, 200):
        if back % 2:
            continue
        distance = (6.5 if persona.key == "alex" else 1.0) + (back % 5) * 0.4
        found.append(
            {
                "id": _id(persona, f"check-running-{back}"),
                "goal_id": weekly,
                "day": today - timedelta(days=back),
                "done": None,
                "value": round(distance, 1),
            }
        )
    savings = _id(persona, "goal-savings")
    for month in range(3):
        found.append(
            {
                "id": _id(persona, f"check-savings-{month}"),
                "goal_id": savings,
                "day": today - timedelta(days=90 - month * 30 - 1),
                "done": None,
                "value": 450 * (month + 1) + (150 if persona.key == "alex" else 0),
            }
        )
    return [{"value": None, **one} for one in found]


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    zone = ZoneInfo(persona.timezone)
    space = next(iter(current_spaces.get()), None)
    await connection.execute(PERSON)
    categories = {key: _id(persona, f"category-{key}") for key, _ in CATEGORIES}
    for position, (key, hue) in enumerate(CATEGORIES, start=1):
        await connection.execute(
            CATEGORY,
            {
                "id": categories[key],
                "name": _name(persona, key),
                "hue": hue,
                "position": position,
                "space_id": None,
            },
        )
    tasks = _done(persona, categories, today, zone) + _pending(persona, categories, today)
    if persona.key == "alex" and space is not None:
        shared = _id(persona, "category-shared")
        await connection.execute(
            CATEGORY,
            {"id": shared, "name": "Household", "hue": 3, "position": 0, "space_id": space},
        )
        tasks += _shared(persona, shared, space, today)
    for one in tasks:
        await connection.execute(TASK, one)
    for one in _goals(persona, categories, today):
        await connection.execute(GOAL, one)
    for one in _checks(persona, today):
        await connection.execute(CHECK, one)
