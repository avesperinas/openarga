import { invalidate, useResource } from "@openarga/app";
import {
  Button,
  Card,
  ChatBubble,
  ChatText,
  ChatThread,
  Composer,
  ConfirmDelete,
  EmptyState,
  ErrorState,
  Hint,
  List,
  ListRow,
  Notice,
  OfflineNotice,
  Screen,
  Skeleton,
  Working,
  useNow,
} from "@openarga/ui";
import { type KeyboardEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  type Message,
  type Thread,
  type ThreadOut,
  Unauthorised,
  askAgain,
  deleteThread,
  readThread,
  readThreads,
  say,
  signIn,
  startThread,
} from "./api";
import { ScreenHeader, useApp } from "./Header";
import { when } from "./words";
import { t } from "./lang";

const POLL_MS = 2500;
export const PATIENCE_MS = 10 * 60 * 1000;

export function stale(thread: Pick<Thread, "waiting_since">, now = Date.now()): boolean {
  return thread.waiting_since !== null && now - new Date(thread.waiting_since).getTime() > PATIENCE_MS;
}

export function threadLine(thread: Thread, name: string): string {
  if (thread.problem) return t("chat.could_not");
  if (thread.waiting_since) return t("chat.thinking", { name });
  return when(thread.updated_at);
}

export function thinkingFor(since: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

export function sends(event: Pick<KeyboardEvent, "key" | "shiftKey" | "nativeEvent">): boolean {
  const composing = (event.nativeEvent as { isComposing?: boolean }).isComposing === true;
  return event.key === "Enter" && !event.shiftKey && !composing;
}

export const THREADS = "threads";

export function ChatList({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const app = useApp();
  const found = useResource(THREADS, readThreads, { persist: true });
  const threads = found.data ?? null;

  return (
    <Screen>
      <ScreenHeader title={t("chat.title")} />
      <Button variant="primary" icon="plus" onClick={onNew}>
        {t("chat.new")}
      </Button>
      <OfflineNotice />
      {found.loading && <Skeleton label={t("chat.loading")} />}
      {threads === null && found.error && (
        <ErrorState
          title={t("chat.failed")}
          detail={found.error.message}
          onRetry={found.refresh}
        />
      )}
      {threads !== null && threads.length === 0 && (
        <EmptyState
          title={t("chat.empty", { name: app.name })}
          action={{ label: t("chat.start"), icon: "plus", onClick: onNew }}
        >
          {t("chat.empty_detail")}
        </EmptyState>
      )}
      {threads !== null && threads.length > 0 && (
        <List>
          {threads.map((thread) => (
            <ListRow
              key={thread.id}
              title={thread.title}
              subtitle={threadLine(thread, app.name)}
              tone={thread.problem ? "warning" : thread.waiting_since ? "positive" : undefined}
              accessory="chevron-right"
              onClick={() => onOpen(thread.id)}
            />
          ))}
        </List>
      )}
    </Screen>
  );
}

type Render = (markdown: string) => string;
let painter: Promise<Render> | null = null;

function loadPainter(): Promise<Render> {
  painter ??= import("@openarga/ui/notes").then((notes) => (markdown: string) => notes.render(markdown));
  return painter;
}

function Bubble({ message }: { message: Message }) {
  const [html, setHtml] = useState<string | null>(null);
  useEffect(() => {
    if (message.author !== "insights") return;
    let live = true;
    void loadPainter().then((paint) => {
      if (live) setHtml(paint(message.body));
    });
    return () => {
      live = false;
    };
  }, [message]);
  return (
    <ChatBubble mine={message.author === "person"}>
      {message.author === "insights" && html !== null ? (
        <div className="mn-prose" dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <ChatText>{message.body}</ChatText>
      )}
    </ChatBubble>
  );
}

function Thinking({ name, since }: { name: string; since: string }) {
  const now = useNow();
  return (
    <ChatBubble mine={false}>
      <Working>
        {t("chat.looking", { name, time: thinkingFor(since, now) })}
      </Working>
    </ChatBubble>
  );
}

export function ThreadScreen({
  id,
  insightId,
  onBack,
  onStarted,
}: {
  id: string | null;
  insightId?: string | null;
  onBack: () => void;
  onStarted: (id: string) => void;
}) {
  const app = useApp();
  const [thread, setThread] = useState<ThreadOut | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState("");
  const [removing, setRemoving] = useState(false);
  const [unopened, setUnopened] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const failed = useCallback((error: unknown, fallback: string) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(fallback);
  }, []);

  useEffect(() => {
    if (id === null) return;
    setUnopened(null);
    void readThread(id)
      .then(setThread)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setUnopened(error instanceof Error ? error.message : "");
      });
  }, [id, attempt]);

  useEffect(() => {
    if (!thread?.waiting_since || stale(thread)) return;
    const timer = window.setTimeout(() => {
      void readThread(thread.id)
        .then((updated) => {
          setThread(updated);
          if (updated.waiting_since !== thread.waiting_since || updated.problem !== thread.problem) invalidate(THREADS);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [thread]);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [thread?.messages.length, thread?.waiting_since, pending]);

  useLayoutEffect(() => {
    const area = box.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = `${area.scrollHeight}px`;
  }, [draft]);

  const waiting = Boolean(thread?.waiting_since) && !(thread && stale(thread));
  const busy = pending !== null || waiting;

  const send = () => {
    const text = draft.trim();
    if (!text || busy) return;
    setProblem("");
    setPending(text);
    setDraft("");
    const sent = thread ? say(thread.id, text) : startThread(text, insightId);
    void sent
      .then((updated) => {
        setThread(updated);
        invalidate(THREADS);
        if (!thread) onStarted(updated.id);
      })
      .catch((error: unknown) => {
        setDraft(text);
        failed(error, t("chat.send_failed"));
      })
      .finally(() => setPending(null));
  };

  const again = () => {
    if (!thread) return;
    setProblem("");
    void askAgain(thread.id)
      .then((updated) => {
        setThread(updated);
        invalidate(THREADS);
      })
      .catch((error: unknown) => failed(error, t("chat.again_failed")));
  };

  const late = thread !== null && stale(thread);
  return (
    <Screen>
      <ScreenHeader title={thread?.title ?? t("chat.new")} back={{ label: t("chat.title"), onClick: onBack }} />

      <OfflineNotice />
      {id !== null && thread === null && unopened === null && <Skeleton label={t("chat.opening")} />}
      {thread === null && unopened !== null && (
        <ErrorState
          title={t("chat.open_failed")}
          detail={unopened || undefined}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      )}

      <ChatThread>
        {thread?.messages.map((message) => (
          <Bubble key={message.id} message={message} />
        ))}
        {pending !== null && (
          <ChatBubble mine sending>
            <ChatText>{pending}</ChatText>
          </ChatBubble>
        )}
        {waiting && thread?.waiting_since && <Thinking name={app.name} since={thread.waiting_since} />}
        <div ref={end} />
      </ChatThread>

      {thread?.problem && (
        <Notice tone="warning" action={{ label: t("chat.ask_again"), onClick: again }}>
          {thread.problem}
        </Notice>
      )}
      {late && !thread?.problem && (
        <Notice tone="warning" action={{ label: t("chat.ask_again"), onClick: again }}>
          {t("chat.late")}
        </Notice>
      )}
      {problem && <Hint tone="warning">{problem}</Hint>}

      <Card>
        <Composer
          inputRef={box}
          label={thread ? t("chat.reply") : t("chat.ask", { name: app.name })}
          value={draft}
          placeholder={insightId && !thread ? t("chat.about_insight") : `${t("chat.ask", { name: app.name })}…`}
          onChange={setDraft}
          onSend={send}
          disabled={busy}
        />
        <Hint>{t("chat.keys")}</Hint>
      </Card>

      {thread && (
        <Button variant="plain" icon="trash" onClick={() => setRemoving(true)}>
          {t("chat.delete")}
        </Button>
      )}
      {removing && thread && (
        <ConfirmDelete
          title={t("chat.delete_confirm")}
          subject={thread.title}
          consequence={t("chat.delete_consequence")}
          action={t("chat.delete")}
          onCancel={() => setRemoving(false)}
          onConfirm={() =>
            deleteThread(thread.id)
              .then(() => {
                invalidate(THREADS);
                onBack();
              })
              .catch((error: unknown) => {
                setRemoving(false);
                failed(error, t("chat.delete_failed"));
              })
          }
        />
      )}
    </Screen>
  );
}
