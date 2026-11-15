import { Button, Card, ConfirmDelete, Icon, IconButton, List, ListRow, Notice, OfflineNotice, Screen, SegmentedControl, TextField } from "@openarga/ui";
import { useCallback, useRef, useState } from "react";

import { type Attachment, type Note, api, fileUrl } from "./api";
import { useNavigate } from "./App";
import { Pending, Problem, Section, changed, useLoad } from "./Bits";
import { ScreenHeader } from "./Header";
import { NoteEditor } from "./LazyEditor";
import { MoveSheet } from "./Sheets";
import { dayTitle, fileSize, isoDate, sessionMoment, span } from "./words";
import { t } from "./lang";

const KIND = { class: "session.kind.class", tutorial: "session.kind.tutorial", event: "session.kind.event" } as const;

export function SessionScreen({ id }: { id: string }) {
  const navigate = useNavigate();
  const [moving, setMoving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [removing, setRemoving] = useState<Attachment | null>(null);
  const [extraNote, setExtraNote] = useState(false);
  const { data, found, setData, problem, fail, refresh } = useLoad(`session:${id}`, () => api.session(id), { fresh: true });
  const files = useRef<HTMLInputElement>(null);

  const onSaved = useCallback(
    (note: Note) =>
      setData((page) =>
        page && !page.notes.some((n) => n.id === note.id)
          ? { ...page, notes: [...page.notes, note], detail: { ...page.detail, session: { ...page.detail.session, has_notes: true } } }
          : page,
      ),
    [setData],
  );

  if (!data) {
    return (
      <Screen>
        <ScreenHeader back={{ label: t("app.name"), onClick: () => navigate({ tab: "home" }) }} />
        <OfflineNotice />
        <Problem text={problem} />
        <Pending found={found} />
      </Screen>
    );
  }

  const { detail } = data;
  const session = detail.session;
  const start = new Date(session.starts_at);
  const moment = sessionMoment(session);
  const cancelled = session.status === "cancelled";
  const place = { course_id: session.course_id, subject_id: session.subject_id, session_id: session.id };
  const back = session.subject_id
    ? { label: detail.subject_name ?? t("field.subject"), onClick: () => navigate({ tab: "subject", id: session.subject_id! }) }
    : { label: detail.course_name, onClick: () => navigate({ tab: "course", id: session.course_id }) };

  const attend = async (value: "present" | "absent" | "none") => {
    try {
      const next = await api.markAttendance(session.id, value === "none" ? null : value);
      setData({ ...data, detail: next });
      changed();
    } catch (error) {
      fail(error);
    }
  };

  const upload = async (list: FileList | null) => {
    for (const file of Array.from(list ?? [])) {
      try {
        await api.uploadFile(file, file.name, { sessionId: session.id });
      } catch (error) {
        fail(error);
      }
    }
    void refresh();
  };

  return (
    <Screen>
      <ScreenHeader
        back={back}
        eyebrow={`${t(KIND[session.kind])} · ${session.kind === "class" ? detail.course_name : session.course}`}
        title={session.kind === "class" ? session.title : session.title}
      />
      <OfflineNotice />
      <Problem text={problem} />

      <Card>
        <p className="study-class-day" data-status={session.status}>
          {dayTitle(isoDate(start))}
          {cancelled ? ` · ${t("session.cancelled")}` : moment === "now" ? ` · ${t("session.now")}` : ""}
        </p>
        <p className="study-class-time" data-status={session.status}>
          {span(session.starts_at, session.ends_at)}
        </p>
        {(session.place || session.url) && (
          <div className="study-class-where">
            {session.place && (
              <span className="study-class-place">
                <Icon name="pin" /> {session.place}
              </span>
            )}
            {session.url && (
              <a className="button" data-variant="primary" href={session.url} target="_blank" rel="noreferrer">
                <Icon name="play" />
                <span className="button-label">{t("session.enter")}</span>
              </a>
            )}
          </div>
        )}
        {detail.phrase && (
          <p className="study-muted">
            {t("session.from_schedule", { phrase: detail.phrase })}
            {detail.touched && ` · ${t("session.touched")}`}
          </p>
        )}
        {!cancelled && moment !== "future" && (
          <SegmentedControl
            label={t("session.went_q")}
            options={[
              { value: "present", label: t("session.went") },
              { value: "absent", label: t("session.missed") },
              { value: "none", label: t("session.unmarked") },
            ]}
            value={session.attendance ?? "none"}
            onChange={(value) => void attend(value)}
          />
        )}
        <TopicField
          key={session.id + (session.topic ?? "")}
          value={session.topic ?? ""}
          onSave={async (topic) => {
            try {
              const next = await api.setTopic(session.id, topic || null);
              setData({ ...data, detail: next });
              changed();
            } catch (error) {
              fail(error);
            }
          }}
        />
        <div className="study-class-nav">
          <IconButton
            icon="chevron-left"
            label={t("session.previous")}
            size="small"
            disabled={!detail.previous_id}
            onClick={() => detail.previous_id && navigate({ tab: "session", id: detail.previous_id }, { replace: true })}
          />
          <Button variant="plain" size="small" onClick={() => setMoving(true)}>
            {session.kind === "class" ? (cancelled ? t("session.restore_move") : t("session.move_cancel")) : t("session.change")}
          </Button>
          <IconButton
            icon="chevron-right"
            label={t("session.next")}
            size="small"
            disabled={!detail.next_id}
            onClick={() => detail.next_id && navigate({ tab: "session", id: detail.next_id }, { replace: true })}
          />
        </div>
      </Card>

      {data.notes_unavailable && (
        <Notice tone="warning" title={t("notes.unavailable")}>
          {data.notes_unavailable} {t("session.notes_unavailable_rest")}
        </Notice>
      )}
      {!data.notes_unavailable && data.notes.length === 0 && (
        <NoteEditor key="new" note={null} place={place} autoFocus={moment === "now"} onSaved={onSaved} onError={fail} />
      )}
      {data.notes.map((note, index) => (
        <NoteEditor
          key={note.id}
          note={note}
          place={place}
          startIn={index === 0 && moment === "now" ? "write" : "read"}
          onSaved={onSaved}
          onError={fail}
        />
      ))}
      {data.notes.length > 0 &&
        (extraNote ? (
          <NoteEditor key="extra" note={null} place={place} autoFocus onSaved={onSaved} onError={fail} />
        ) : (
          <Button variant="plain" size="small" icon="plus" onClick={() => setExtraNote(true)}>
            {t("session.more_notes")}
          </Button>
        ))}

      <Section
        title={t("files.title")}
        count={data.files.length}
        action={{ label: t("files.upload"), icon: "plus", onClick: () => files.current?.click() }}
      >
        <input ref={files} type="file" multiple hidden onChange={(event) => void upload(event.target.files)} />
        {data.files.length === 0 ? (
          <p className="study-muted">{t("files.empty")}</p>
        ) : (
          <List>
            {data.files.map((file) => (
              <ListRow
                key={file.id}
                title={file.filename}
                subtitle={`${file.filename.split(".").pop()?.slice(0, 4).toUpperCase() ?? ""} · ${fileSize(file.size)}`}
                image={file.is_image ? fileUrl(file.id) : undefined}
                icon={file.is_image ? undefined : "file"}
                onClick={() => window.open(fileUrl(file.id), "_blank", "noreferrer")}
                action={{ icon: "trash", label: t("files.delete_label", { name: file.filename }), onClick: () => setRemoving(file) }}
              />
            ))}
          </List>
        )}
      </Section>

      {moving && (
        <MoveSheet
          session={session}
          onClose={() => setMoving(false)}
          onSaved={() => {
            setMoving(false);
            void refresh();
          }}
          onDelete={session.kind !== "class" || !detail.schedule_id ? () => setDeleting(true) : undefined}
          onError={fail}
        />
      )}
      {deleting && (
        <ConfirmDelete
          title={t("session.delete_title")}
          subject={`${session.title} · ${dayTitle(isoDate(start))}`}
          consequence={data.notes.length ? t("session.delete_consequence") : undefined}
          action={t("session.delete")}
          onCancel={() => setDeleting(false)}
          onConfirm={async () => {
            await api.deleteSession(session.id);
            changed();
            back.onClick();
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title={t("files.delete_title")}
          subject={removing.filename}
          action={t("files.delete")}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await api.deleteFile(removing.id);
            setRemoving(null);
            void refresh();
          }}
        />
      )}
    </Screen>
  );
}

function TopicField({ value, onSave }: { value: string; onSave: (topic: string) => Promise<void> }) {
  const [topic, setTopic] = useState(value);
  return (
    <TextField
      label={t("session.topic")}
      value={topic}
      onChange={setTopic}
      placeholder={t("session.topic_placeholder")}
      onBlur={() => topic.trim() !== value && void onSave(topic.trim())}
      onSubmit={() => topic.trim() !== value && void onSave(topic.trim())}
    />
  );
}
