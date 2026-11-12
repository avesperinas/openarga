import { Unauthorised, createApi, problemOf, signIn } from "@openarga/app";
import type { RecurrenceRule } from "@openarga/ui";

export type Track = "grades" | "progress" | "attendance";
export type Kind = "master" | "degree" | "course" | "certification" | "language" | "other";
export type Modality = "in_person" | "online" | "hybrid";
export type CourseStatus = "planned" | "active" | "finished" | "abandoned";
export type AssessmentKind = "assignment" | "exam" | "practical" | "participation" | "other";
export type AssessmentStatus = "pending" | "submitted" | "graded";
export type Tone = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;

export type Verdict =
  | "empty"
  | "not_started"
  | "in_progress"
  | "secured"
  | "impossible"
  | "passed"
  | "failed"
  | "below_minimum";

export interface Minimum {
  title: string;
  min_grade: number;
}

export interface Grade {
  verdict: Verdict;
  current: number | null;
  secured: number | null;
  graded_weight: number;
  remaining_weight: number;
  needed_to_pass: number | null;
  needed_for_target: number | null;
  target: number | null;
  final: number | null;
  final_source: "record" | "computed" | null;
  unweighted: number;
  failed_minimums: Minimum[];
  pending_minimums: Minimum[];
  sentence: string;
}

export interface CourseGrade {
  average: number | null;
  average_source: "record" | "subjects" | "assessments" | null;
  counted: number;
  subjects: number;
}

export interface Progress {
  kind: "credits" | "hours" | "subjects" | "time";
  done: number;
  total: number;
  ratio: number;
  label: string;
}

export interface Attendance {
  present: number;
  absent: number;
  unmarked: number;
  past: number;
  ratio: number | null;
}

export interface Session {
  id: string;
  course_id: string;
  subject_id: string | null;
  kind: "class" | "tutorial" | "event";
  title: string;
  starts_at: string;
  ends_at: string;
  place: string | null;
  url: string | null;
  status: "scheduled" | "cancelled";
  attendance: "present" | "absent" | null;
  topic: string | null;
  tone: Tone;
  course: string;
  has_notes: boolean;
}

export interface Assessment {
  id: string;
  course_id: string;
  subject_id: string | null;
  subject: string | null;
  course: string;
  tone: Tone;
  title: string;
  kind: AssessmentKind;
  due_on: string | null;
  due_time: string | null;
  weight: number | null;
  min_grade: number | null;
  status: AssessmentStatus;
  grade: number | null;
  note: string | null;
  scale_max: number;
  pass_mark: number;
  days_left: number | null;
}

export interface Subject {
  id: string;
  course_id: string;
  name: string;
  teacher: string | null;
  credits: number | null;
  period: string | null;
  final_grade: number | null;
  position: number;
  grade: Grade;
  assessments: number;
}

export interface Course {
  id: string;
  name: string;
  kind: Kind;
  institution: string | null;
  modality: Modality;
  starts_on: string | null;
  ends_on: string | null;
  status: CourseStatus;
  credits: number | null;
  hours: number | null;
  scale_max: number;
  pass_mark: number;
  target_grade: number | null;
  final_grade: number | null;
  tone: Tone;
  campus_url: string | null;
  tz: string;
  note: string | null;
  tracks: Track[];
  closed_on: string | null;
  has_certificate: boolean;
  certificate_name: string | null;
  average: CourseGrade;
  grade: Grade | null;
  progress: Progress | null;
  attendance: Attendance;
  subjects: number;
  next_session: Session | null;
}

export interface CourseDetail {
  course: Course;
  subjects: Subject[];
  assessments: Assessment[];
}

export interface Day {
  date: string;
  today: boolean;
  sessions: Session[];
  assessments: Assessment[];
}

export interface Home {
  week_start: string;
  days: Day[];
  upcoming: Assessment[];
  courses: Course[];
  archived: number;
}

export interface ServerRule {
  freq: RecurrenceRule["freq"];
  interval: number;
  by_day: { weekday: string; pos?: number | null }[];
  by_month_day: number[];
  by_month: number[];
  count: number | null;
  until: string | null;
}

export interface Schedule {
  id: string;
  course_id: string;
  subject_id: string | null;
  subject: string | null;
  rrule: string;
  rule: ServerRule;
  phrase: string;
  starts_on: string;
  ends_on: string | null;
  start_time: string;
  end_time: string;
  place: string | null;
  url: string | null;
  sessions: number;
}

export interface NoteBrief {
  id: string;
  course_id: string;
  subject_id: string | null;
  session_id: string | null;
  title: string;
  excerpt: string;
  course: string;
  subject: string | null;
  tone: Tone;
  session_start: string | null;
  created_at: string;
  updated_at: string;
  words: number;
  folder: string;
}

export interface Note extends NoteBrief {
  body: string;
}

export interface Hit extends NoteBrief {
  fragment: string;
  rank: number;
}

export interface Material {
  id: string;
  course_id: string;
  subject_id: string | null;
  subject: string | null;
  title: string;
  url: string | null;
  attachment_id: string | null;
  filename: string | null;
  content_type: string | null;
  size: number | null;
  created_at: string;
}

export interface Attachment {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  is_image: boolean;
  url: string;
  created_at: string;
}

export interface SubjectDetail {
  subject: Subject;
  course: Course;
  assessments: Assessment[];
  sessions: Session[];
  notes: NoteBrief[];
  notes_unavailable?: string | null;
  materials: Material[];
  schedules: Schedule[];
}

export interface SessionDetail {
  session: Session;
  course_name: string;
  subject_name: string | null;
  tz: string;
  schedule_id: string | null;
  phrase: string | null;
  touched: boolean;
  previous_id: string | null;
  next_id: string | null;
}

export interface SessionPage {
  detail: SessionDetail;
  notes: Note[];
  notes_unavailable?: string | null;
  files: Attachment[];
}

export interface SubjectIn {
  name: string;
  teacher?: string | null;
  credits?: number | null;
  period?: string | null;
}

export interface CourseIn {
  name: string;
  kind: Kind;
  institution: string | null;
  modality: Modality;
  starts_on: string | null;
  ends_on: string | null;
  status: "planned" | "active";
  credits: number | null;
  hours: number | null;
  scale_max: 10 | 100;
  pass_mark: number | null;
  target_grade: number | null;
  tone: Tone;
  campus_url: string | null;
  note: string | null;
  tracks?: Track[];
  subjects?: SubjectIn[];
  final_grade?: number | null;
}

export interface AssessmentIn {
  title: string;
  kind: AssessmentKind;
  subject_id: string | null;
  due_on: string | null;
  due_time: string | null;
  weight: number | null;
  min_grade: number | null;
  status: AssessmentStatus;
  grade: number | null;
  note: string | null;
}

export interface ScheduleIn {
  subject_id: string | null;
  rule: ServerRule;
  starts_on: string;
  start_time: string;
  end_time: string;
  place: string | null;
  url: string | null;
}

export interface SessionIn {
  kind: "class" | "tutorial" | "event";
  title: string | null;
  subject_id: string | null;
  starts_at: string;
  ends_at: string;
  place: string | null;
  url: string | null;
}

export interface SessionEdit {
  starts_at: string;
  ends_at: string;
  place: string | null;
  url: string | null;
  status: "scheduled" | "cancelled";
  title: string | null;
}

const client = createApi("study");
const { get, send } = client;
const BASE = client.base;

export { Unauthorised, signIn };

async function upload<T>(path: string, file: Blob, method = "POST"): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: { "content-type": file.type || "application/octet-stream", accept: "application/json" },
    body: file,
  });
  if (response.status === 401) throw new Unauthorised("sin sesión");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(problemOf(body) ?? `${path}: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const readVersion = client.readVersion;

const q = encodeURIComponent;

export const api = {
  home: (week?: string) => get<Home>(week ? `/home?week=${week}` : "/home"),
  courses: (scope: "current" | "archive" | "all" = "current") => get<Course[]>(`/courses?scope=${scope}`),
  course: (id: string) => get<CourseDetail>(`/courses/${id}`),
  createCourse: (body: CourseIn) => send<CourseDetail>("/courses", "POST", body),
  updateCourse: (id: string, body: CourseIn) => send<CourseDetail>(`/courses/${id}`, "PUT", body),
  closeCourse: (id: string, body: { status: "finished" | "abandoned"; closed_on: string | null; final_grade: number | null }) =>
    send<CourseDetail>(`/courses/${id}/close`, "POST", body),
  reopenCourse: (id: string) => send<CourseDetail>(`/courses/${id}/reopen`, "POST"),
  deleteCourse: (id: string) => send<void>(`/courses/${id}`, "DELETE"),
  uploadCertificate: (id: string, file: File) =>
    upload<Attachment>(`/courses/${id}/certificate?filename=${q(file.name)}`, file, "PUT"),

  subject: (id: string) => get<SubjectDetail>(`/subjects/${id}`),
  addSubject: (courseId: string, body: SubjectIn) => send<Subject>(`/courses/${courseId}/subjects`, "POST", body),
  updateSubject: (id: string, body: SubjectIn) => send<Subject>(`/subjects/${id}`, "PUT", body),
  recordGrade: (id: string, grade: number | null) =>
    send<Subject>(`/subjects/${id}/record`, "PUT", { final_grade: grade }),
  deleteSubject: (id: string) => send<void>(`/subjects/${id}`, "DELETE"),

  schedules: (courseId: string) => get<Schedule[]>(`/courses/${courseId}/schedules`),
  addSchedule: (courseId: string, body: ScheduleIn) => send<Schedule>(`/courses/${courseId}/schedules`, "POST", body),
  updateSchedule: (id: string, body: ScheduleIn) => send<Schedule>(`/schedules/${id}`, "PUT", body),
  deleteSchedule: (id: string) => send<{ removed_sessions: number }>(`/schedules/${id}`, "DELETE"),

  sessions: (from: string, to: string) => get<Session[]>(`/sessions?from=${q(from)}&to=${q(to)}`),
  courseSessions: (courseId: string) => get<Session[]>(`/courses/${courseId}/sessions`),
  session: (id: string) => get<SessionPage>(`/sessions/${id}`),
  addSession: (courseId: string, body: SessionIn) =>
    send<SessionDetail>(`/courses/${courseId}/sessions`, "POST", body),
  updateSession: (id: string, body: SessionEdit) => send<SessionDetail>(`/sessions/${id}`, "PUT", body),
  markAttendance: (id: string, attendance: "present" | "absent" | null) =>
    send<SessionDetail>(`/sessions/${id}/attendance`, "PUT", { attendance }),
  setTopic: (id: string, topic: string | null) => send<SessionDetail>(`/sessions/${id}/topic`, "PUT", { topic }),
  deleteSession: (id: string) => send<void>(`/sessions/${id}`, "DELETE"),

  assessment: (id: string) => get<Assessment>(`/assessments/${id}`),
  assessmentsBetween: (from: string, to: string) => get<Assessment[]>(`/assessments?from=${from}&to=${to}`),
  addAssessment: (courseId: string, body: AssessmentIn) =>
    send<Assessment>(`/courses/${courseId}/assessments`, "POST", body),
  updateAssessment: (id: string, body: AssessmentIn) => send<Assessment>(`/assessments/${id}`, "PUT", body),
  gradeAssessment: (id: string, grade: number | null, status: "pending" | "submitted" = "submitted") =>
    send<Assessment>(`/assessments/${id}/grade`, "PUT", { grade, status }),
  deleteAssessment: (id: string) => send<void>(`/assessments/${id}`, "DELETE"),

  notes: (filter: { courseId?: string; subjectId?: string } = {}) => {
    const params = new URLSearchParams();
    if (filter.courseId) params.set("course_id", filter.courseId);
    if (filter.subjectId) params.set("subject_id", filter.subjectId);
    const query = params.toString();
    return get<NoteBrief[]>(query ? `/notes?${query}` : "/notes");
  },
  search: (text: string) => get<Hit[]>(`/notes?q=${q(text)}`),
  note: (id: string) => get<Note>(`/notes/${id}`),
  addNote: (body: { course_id: string; subject_id?: string | null; session_id?: string | null; title?: string; body?: string }) =>
    send<Note>("/notes", "POST", body),
  updateNote: (id: string, body: { title: string; body: string; subject_id?: string | null }) =>
    send<Note>(`/notes/${id}`, "PUT", body),
  deleteNote: (id: string) => send<void>(`/notes/${id}`, "DELETE"),

  uploadFile: (file: Blob, name: string, place: { noteId?: string; sessionId?: string } = {}) => {
    const params = new URLSearchParams({ filename: name });
    if (place.noteId) params.set("note_id", place.noteId);
    if (place.sessionId) params.set("session_id", place.sessionId);
    return upload<Attachment>(`/attachments?${params.toString()}`, file);
  },
  deleteFile: (id: string) => send<void>(`/attachments/${id}`, "DELETE"),

  materials: (courseId: string) => get<Material[]>(`/courses/${courseId}/materials`),
  addLink: (courseId: string, body: { title: string; url: string; subject_id: string | null }) =>
    send<Material>(`/courses/${courseId}/materials`, "POST", body),
  addFile: (courseId: string, file: File, subjectId: string | null) => {
    const params = new URLSearchParams({ filename: file.name });
    if (subjectId) params.set("subject_id", subjectId);
    return upload<Material>(`/courses/${courseId}/materials/file?${params.toString()}`, file);
  },
  deleteMaterial: (id: string) => send<void>(`/materials/${id}`, "DELETE"),
};

export const fileUrl = (id: string, download = false) =>
  `${BASE}/attachments/${id}${download ? "?download=true" : ""}`;
