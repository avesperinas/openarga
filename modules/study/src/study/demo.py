from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_recurrence import Day, Rule
from study import studies, timetable
from study.studies import AssessmentIn, CourseIn, SubjectIn

PAST = (
    ("Linear algebra", 6, 8.4, "Dr Moreau"),
    ("Programming for data", 6, 9.1, "Dr Ibarra"),
    ("Databases", 6, 8.0, "Dr Salazar"),
    ("Probability", 6, 7.2, "Dr Vidal"),
    ("Foundations of ML", 6, 8.8, "Dr Moreau"),
)
NUTRITION = (
    ("Biochemistry of food", 6, 7.8, "Dr Carbonell"),
    ("Sports nutrition", 4, 9.0, "Dr Elizalde"),
    ("Clinical dietetics", 6, None, "Dr Carbonell"),
    ("Food safety", 4, None, "Dr Lizarraga"),
)


def _courses(persona: Persona, today: date) -> list[CourseIn]:
    if persona.key == "alex":
        return [
            CourseIn(
                name="Master in Data Science",
                kind="master",
                institution="An invented university",
                modality="hybrid",
                starts_on=today - timedelta(days=320),
                ends_on=today + timedelta(days=240),
                credits=90,
                target_grade=8.5,
                tone=3,
                tz=persona.timezone,
                subjects=[
                    SubjectIn(name=name, credits=credits, teacher=teacher, period="Semester 1")
                    for name, credits, _, teacher in PAST
                ]
                + [
                    SubjectIn(
                        name="Statistics", credits=6, teacher="Dr Example", period="Semester 2"
                    ),
                    SubjectIn(name="Machine learning", credits=6, period="Semester 2"),
                    SubjectIn(
                        name="Data engineering", credits=6, teacher="Dr Arana", period="Semester 2"
                    ),
                    SubjectIn(
                        name="Optimisation", credits=6, teacher="Dr Vidal", period="Semester 2"
                    ),
                ],  # fmt: skip
            ),
            CourseIn(
                name="German B1 evening course",
                kind="language",
                institution="Goethe corner school",
                modality="in_person",
                starts_on=today - timedelta(days=75),
                ends_on=today + timedelta(days=105),
                hours=120,
                tone=8,
                tz=persona.timezone,
            ),
            CourseIn(
                name="Cloud fundamentals certification",
                kind="certification",
                institution="Online academy",
                modality="online",
                starts_on=today - timedelta(days=260),
                ends_on=today - timedelta(days=200),
                hours=30,
                tone=5,
                tz=persona.timezone,
            ),
        ]
    return [
        CourseIn(
            name="Italian A2",
            kind="language",
            institution="A language school",
            modality="in_person",
            starts_on=today - timedelta(days=90),
            ends_on=today + timedelta(days=120),
            hours=80,
            tone=6,
            tz=persona.timezone,
        ),
        CourseIn(
            name="Postgraduate certificate in Nutrition",
            kind="course",
            institution="An invented university",
            modality="online",
            starts_on=today - timedelta(days=200),
            ends_on=today + timedelta(days=150),
            credits=20,
            target_grade=8,
            tone=2,
            tz=persona.timezone,
            subjects=[
                SubjectIn(name=name, credits=credits, teacher=teacher)
                for name, credits, _, teacher in NUTRITION
            ],
        ),
        CourseIn(
            name="Pottery workshop",
            kind="other",
            institution="Taller Arcilla",
            modality="in_person",
            starts_on=today - timedelta(days=400),
            ends_on=today - timedelta(days=340),
            hours=24,
            tone=4,
            tz=persona.timezone,
        ),
    ]


def _assessments(
    persona: Persona, today: date, course: str, subjects: dict[str, str]
) -> list[AssessmentIn]:
    if course == "Master in Data Science":
        stats, learning = subjects["Statistics"], subjects["Machine learning"]
        eng, opt = subjects["Data engineering"], subjects["Optimisation"]
        found = [
            AssessmentIn(title="Lab 1", kind="practical", subject_id=stats, weight=20, grade=7.5,
                         due_on=today - timedelta(days=14), status="graded"),
            AssessmentIn(title="Lab 2", kind="practical", subject_id=stats, weight=20,
                         due_on=today + timedelta(days=3), due_time=time(23, 59)),
            AssessmentIn(title="Final exam", kind="exam", subject_id=stats, weight=60, min_grade=4,
                         due_on=today + timedelta(days=45)),
            AssessmentIn(title="Project", kind="assignment", subject_id=learning, weight=50,
                         due_on=today + timedelta(days=20)),
            AssessmentIn(title="Quiz 1", kind="exam", subject_id=learning, weight=20, grade=8.8,
                         due_on=today - timedelta(days=30), status="graded"),
            AssessmentIn(title="Pipeline case study", kind="assignment", subject_id=eng,
                         weight=40, grade=9.2, due_on=today - timedelta(days=21), status="graded"),
            AssessmentIn(title="Streaming lab", kind="practical", subject_id=eng, weight=30,
                         due_on=today + timedelta(days=12), status="submitted"),
            AssessmentIn(title="Midterm", kind="exam", subject_id=opt, weight=40, grade=6.8,
                         due_on=today - timedelta(days=40), status="graded"),
            AssessmentIn(title="Participation", kind="participation", subject_id=opt, weight=10,
                         due_on=today + timedelta(days=60)),
        ]  # fmt: skip
        for name, _, grade, _ in PAST:
            found += [
                AssessmentIn(title=f"{name}: exam", kind="exam", subject_id=subjects[name],
                             weight=70, grade=grade,
                             due_on=today - timedelta(days=200), status="graded"),
                AssessmentIn(title=f"{name}: coursework", kind="assignment",
                             subject_id=subjects[name], weight=30, grade=min(10, grade + 0.5),
                             due_on=today - timedelta(days=230), status="graded"),
            ]  # fmt: skip
        return found
    if course == "Postgraduate certificate in Nutrition":
        found = []
        for name, _, grade, _ in NUTRITION:
            if grade is None:
                found.append(
                    AssessmentIn(title=f"{name}: report", kind="assignment",
                                 subject_id=subjects[name], weight=60,
                                 due_on=today + timedelta(days=25 if "Clinical" in name else 70))
                )  # fmt: skip
            else:
                found.append(
                    AssessmentIn(title=f"{name}: exam", kind="exam", subject_id=subjects[name],
                                 weight=100, grade=grade, due_on=today - timedelta(days=90),
                                 status="graded")
                )  # fmt: skip
        return found
    if course == "Italian A2":
        return [
            AssessmentIn(title="Unit 3 quiz", kind="exam", weight=25, grade=8.5,
                         due_on=today - timedelta(days=35), status="graded"),
            AssessmentIn(title="Oral presentation", kind="practical", weight=25,
                         due_on=today + timedelta(days=14)),
            AssessmentIn(title="Final test", kind="exam", weight=50,
                         due_on=today + timedelta(days=100)),
        ]  # fmt: skip
    return []


def _schedule(
    persona: Persona, today: date, course: str, subjects: dict[str, str]
) -> list[timetable.ScheduleIn]:
    start = today - timedelta(days=today.weekday())
    if course == "Master in Data Science":
        return [
            timetable.ScheduleIn(
                subject_id=subjects["Statistics"],
                rule=Rule(freq="weekly", by_day=(Day(weekday="TU"), Day(weekday="TH"))),
                starts_on=start,
                start_time=time(18),
                end_time=time(20),
                place="Room 2.3",
            ),
            timetable.ScheduleIn(
                subject_id=subjects["Data engineering"],
                rule=Rule(freq="weekly", by_day=(Day(weekday="WE"),)),
                starts_on=start,
                start_time=time(18),
                end_time=time(19, 30),
                place="Online",
            ),
        ]
    if course == "German B1 evening course":
        return [
            timetable.ScheduleIn(
                rule=Rule(freq="weekly", by_day=(Day(weekday="MO"), Day(weekday="WE"))),
                starts_on=start,
                start_time=time(20),
                end_time=time(21, 30),
                place="Goethe corner school",
            )
        ]
    if course == "Italian A2":
        return [
            timetable.ScheduleIn(
                rule=Rule(freq="weekly", by_day=(Day(weekday="WE"),)),
                starts_on=start,
                start_time=time(19),
                end_time=time(20, 30),
            )
        ]
    if course == "Postgraduate certificate in Nutrition":
        return [
            timetable.ScheduleIn(
                subject_id=subjects["Clinical dietetics"],
                rule=Rule(freq="weekly", by_day=(Day(weekday="TU"),)),
                starts_on=start,
                start_time=time(17),
                end_time=time(18, 30),
                place="Online",
            )
        ]
    return []


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    existing = {one.name for one in await studies.courses(connection, "all")}
    for wanted in _courses(persona, today):
        if wanted.name in existing:
            continue
        created = await studies.create_course(connection, wanted)
        course_id = created.course.id
        subjects = {one.name: one.id for one in created.subjects}
        for item in _assessments(persona, today, wanted.name, subjects):
            await studies.add_assessment(connection, course_id, item)
        finals = {**{name: grade for name, _, grade, _ in (*PAST, *NUTRITION)}}
        for name, subject_id in subjects.items():
            if finals.get(name) is not None:
                await studies.record_grade(
                    connection, subject_id, studies.RecordIn(final_grade=finals[name])
                )
        for block in _schedule(persona, today, wanted.name, subjects):
            until = wanted.ends_on or today + timedelta(days=120)
            block.rule = block.rule.model_copy(update={"until": until})
            await timetable.add_schedule(connection, course_id, block)
        if wanted.ends_on and wanted.ends_on < today:
            await studies.close_course(
                connection,
                course_id,
                studies.CloseIn(
                    status="finished",
                    closed_on=wanted.ends_on,
                    final_grade=8.6 if persona.key == "alex" else 9.2,
                ),
            )
