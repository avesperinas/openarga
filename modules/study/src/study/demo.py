from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_recurrence import Day, Rule
from study import studies, timetable
from study.studies import AssessmentIn, CourseIn, SubjectIn


def _course(persona: Persona, today: date) -> CourseIn:
    if persona.key == "alex":
        return CourseIn(
            name="Master in Data Science",
            kind="master",
            institution="An invented university",
            modality="hybrid",
            starts_on=today - timedelta(days=60),
            ends_on=today + timedelta(days=240),
            credits=60,
            tone=3,
            tz=persona.timezone,
            subjects=[
                SubjectIn(name="Statistics", credits=6, teacher="Dr Example"),
                SubjectIn(name="Machine learning", credits=6),
            ],
        )
    return CourseIn(
        name="Italian A2",
        kind="language",
        institution="A language school",
        modality="in_person",
        starts_on=today - timedelta(days=30),
        tone=6,
        tz=persona.timezone,
    )


def _assessments(persona: Persona, today: date, subjects: dict[str, str]) -> list[AssessmentIn]:
    if persona.key != "alex":
        return []
    stats, learning = subjects["Statistics"], subjects["Machine learning"]
    return [
        AssessmentIn(
            title="Lab 1",
            kind="practical",
            subject_id=stats,
            weight=20,
            grade=7.5,
            due_on=today - timedelta(days=14),
        ),
        AssessmentIn(
            title="Lab 2",
            kind="practical",
            subject_id=stats,
            weight=20,
            due_on=today + timedelta(days=3),
            due_time=time(23, 59),
        ),
        AssessmentIn(
            title="Final exam",
            kind="exam",
            subject_id=stats,
            weight=60,
            min_grade=4,
            due_on=today + timedelta(days=45),
        ),
        AssessmentIn(
            title="Project",
            kind="assignment",
            subject_id=learning,
            weight=50,
            due_on=today + timedelta(days=20),
        ),
    ]


def _schedule(
    persona: Persona, today: date, subjects: dict[str, str]
) -> list[timetable.ScheduleIn]:
    start = today - timedelta(days=today.weekday())
    if persona.key == "alex":
        return [
            timetable.ScheduleIn(
                subject_id=subjects["Statistics"],
                rule=Rule(freq="weekly", by_day=(Day(weekday="TU"), Day(weekday="TH"))),
                starts_on=start,
                start_time=time(18),
                end_time=time(20),
                place="Room 2.3",
            )
        ]
    return [
        timetable.ScheduleIn(
            rule=Rule(freq="weekly", by_day=(Day(weekday="WE"),)),
            starts_on=start,
            start_time=time(19),
            end_time=time(20, 30),
        )
    ]


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    wanted = _course(persona, today)
    if any(one.name == wanted.name for one in await studies.courses(connection, "all")):
        return
    created = await studies.create_course(connection, wanted)
    course_id = created.course.id
    subjects = {one.name: one.id for one in created.subjects}
    for item in _assessments(persona, today, subjects):
        await studies.add_assessment(connection, course_id, item)
    for block in _schedule(persona, today, subjects):
        until = wanted.ends_on or today + timedelta(days=120)
        block.rule = block.rule.model_copy(update={"until": until})
        await timetable.add_schedule(connection, course_id, block)
