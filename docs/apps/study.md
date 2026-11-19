# Study

Courses, classes, exams and grades. A course (a master, a degree, a short course, a certification
or a language) has its subjects, a schedule that generates every session of the period, its
assessments with their weight, and the notes of each session, which live in Notebook. Study tells
you what grade you need in what is left to pass or to reach your target.

Module id `study`, schema `study`, role `mod_study`. Code in
[`modules/study`](../../modules/study), manifest in
[`manifest.yaml`](../../modules/study/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/study/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/study/` | Your courses, what you have to do, and this week's sessions and deadlines |
| `/study/course/<id>` | A course: its figures (average, progress, attendance), assessments, schedule, subjects, notes and materials |
| `/study/subject/<id>` | A subject: its grade meter and what you need, its assessments, sessions, notes and materials |
| `/study/session/<id>` | A session: when and where, attendance, topic, its notes and files |
| `/study/assessment/<id>` | Opens the subject (or the course) the assessment belongs to |
| `/study/notes`, `/study/notes/<id>` | Every note, grouped by course, with search; one note in the editor |
| `/study/archive` | Finished and abandoned courses, with their grade and certificate |
| `/study/settings` | The app's settings |

The old Spanish paths (`/study/estudio/<id>`, `/asignatura/<id>`, `/clase/<id>`, `/apuntes`...)
still open their screen.

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale.
Server texts that reach the person (grade sentences, progress labels, widgets, the home panel,
notifications, calendar titles, default note titles) come from `src/study/i18n/{en,es}.json`.
"Today" follows the person's time zone; each course keeps its own zone for its session times, the
person's zone by default.

## Grades

- An assessment has a weight (percent of its subject's grade), an optional minimum grade and a
  grade on the course's scale (0 to 10 or 0 to 100).
- For each subject Study computes the grade so far, what is secured, the percent left and the
  average needed in what is left to pass and to reach the target, and sums it up in one sentence
  ("You need 6.2 on average in what is left (40 %) to pass."). Missing a minimum fails the
  subject even if the average passes; the record grade overrides the computed one.
- The course average weighs by credits the subjects with a final grade.
- What a course tracks (`grades`, `progress`, `attendance`) is chosen per course: a language with
  no exam in sight tracks none.

## Schedule, sessions and notes

- A schedule block repeats with a recurrence rule and generates its sessions for the whole
  period. Changing a block moves its future untouched sessions; a session that was touched (moved,
  cancelled, with attendance, topic, notes or files) stays as it is.
- Notes are Notebook notes in the course's folder (`Study/<course>/<subject>`), written through the
  `notes.*` capabilities, with `study_course`, `study_subject` and `study_session` in their
  properties. Anything else in that folder shows in the course too.
- Sessions and dated assessments go to the calendar (`agenda` contract); moving one in Planner moves
  it here (`agenda.move`).

## Tools

Read (`study:read`): `get_courses`, `get_week`, `get_grades`, `find_notes`, `get_course`,
`get_note`. Write (`study:write`): `create_course`, `update_course`, `archive_course`,
`reopen_course`, `delete_course`, `add_subject`, `update_subject`, `delete_subject`,
`add_schedule`, `update_schedule`, `delete_schedule`, `add_session`, `update_session`,
`delete_session`, `mark_attendance`, `add_assessment`, `update_assessment`, `delete_assessment`,
`record_grade`, `add_note`, `update_note`, `delete_note`, `add_material`, `delete_material`. Their
descriptions are in the [manifest](../../modules/study/manifest.yaml). `create_course` builds a
whole course from its syllabus in one call.

## What it shares with other apps

- **Uses**: `notes.list`, `notes.read`, `notes.create`, `notes.write`, `notes.trash` (Notebook) and
  `notify.sync`.
- **Publishes**: `study.session` and `study.assessment` (`agenda`), `study.record` (`record`: a
  card per course and subject, and a day record with its sessions and deadlines) and
  `study.metric` (`metric`: progress, average, subjects passed, finished and passed).
- **Provides**: `agenda.move`.
- **Notifications**: the evening before a pending assessment.
- **Home**: widgets for what is up next, progress and the average, and a panel.

## Demo

[`src/study/demo.py`](../../modules/study/src/study/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): Alex has a master with a finished semester (graded subjects) and a current one with graded, submitted and pending assessments, a German evening course and a finished certification; Sam has Italian, a nutrition postgraduate certificate with grades and a finished pottery workshop. Timetables fill the week.
