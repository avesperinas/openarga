import {
  Button,
  ChoiceChips,
  ConfirmDelete,
  DateField,
  fromRRule,
  RecurrencePicker,
  type RecurrenceRule,
  Sheet,
  TextField,
  toRRule,
} from "@openarga/ui";
import { useMemo, useState } from "react";

import { type Task, createTask, removeTask, updateTask } from "./api";
import { Problem, useBusy, useCategories } from "./Parts";
import { clock, quickDates } from "./words";

const OTHER = "other";

export function TaskSheet({
  task,
  category,
  today,
  onClose,
  onSaved,
}: {
  task?: Task;
  category?: string;
  today: string;
  onClose: () => void;
  onSaved: (task: Task | null) => void;
}) {
  const { list } = useCategories();
  const [title, setTitle] = useState(task?.title ?? "");
  const [categoryId, setCategoryId] = useState(task?.category_id ?? category ?? list[0]?.id ?? "");
  const [due, setDue] = useState<string | null>(task?.due_on ?? null);
  const [time, setTime] = useState(task?.due_time ? clock(task.due_time) : "");
  const [rule, setRule] = useState<RecurrenceRule | null>(task?.rule ? fromRRule(task.rule) : null);
  const [notes, setNotes] = useState(task?.notes ?? "");
  const [picking, setPicking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { busy, error, run } = useBusy();

  const quick = useMemo(() => quickDates(today), [today]);
  const chosen = quick.find((one) => one.value === due);
  const dateKey = picking || (!chosen && due) ? OTHER : (chosen?.key ?? "none");

  const choose = (key: string) => {
    if (key === OTHER) {
      setPicking(true);
      if (!due) setDue(today);
      return;
    }
    setPicking(false);
    const value = quick.find((one) => one.key === key)?.value ?? null;
    setDue(value);
    if (!value) {
      setTime("");
      setRule(null);
    }
  };

  const save = () =>
    void run(async () => {
      const body = {
        category_id: categoryId,
        title: title.trim(),
        notes: notes.trim() || null,
        due_on: due,
        due_time: due && time ? time : null,
        rule: due && rule ? toRRule(rule) : null,
      };
      onSaved(task ? await updateTask(task.id, body) : await createTask(body));
    }, "No se ha podido guardar");

  if (deleting && task) {
    return (
      <ConfirmDelete
        title="¿Borrar esta tarea?"
        subject={task.title}
        consequence={
          task.repeats
            ? "Se borra esta y deja de repetirse. Las ya hechas se quedan en Hechas."
            : undefined
        }
        action="Borrar tarea"
        onCancel={() => setDeleting(false)}
        onConfirm={async () => {
          await removeTask(task.id);
          onSaved(null);
        }}
      />
    );
  }

  return (
    <Sheet
      title={task ? "Tarea" : "Nueva tarea"}
      onClose={onClose}
      action={{
        label: busy ? "Guardando…" : task ? "Guardar" : "Añadir",
        onClick: save,
        disabled: busy || !title.trim() || !categoryId,
      }}
    >
      <div className="goals-form">
        <TextField
          label="Qué hay que hacer"
          value={title}
          placeholder="Pedir cita para la ITV"
          autoFocus={!task}
          onChange={setTitle}
          onSubmit={title.trim() && categoryId ? save : undefined}
        />
        <ChoiceChips
          label="Categoría"
          options={list.map((one) => ({ value: one.id, label: one.name }))}
          value={categoryId || null}
          onChange={setCategoryId}
        />
        <ChoiceChips
          label="Para cuándo"
          options={[
            ...quick.map((one) => ({ value: one.key, label: one.label })),
            { value: OTHER, label: "Otro día" },
          ]}
          value={dateKey}
          onChange={choose}
        />
        {dateKey === OTHER && (
          <DateField label="Día" value={due ?? ""} onChange={(value) => setDue(value || null)} />
        )}
        {due && (
          <>
            <TextField
              label="Hora"
              type="time"
              value={time}
              hint={time ? undefined : "Sin hora, vence al acabar el día."}
              onChange={setTime}
            />
            <RecurrencePicker date={due} value={rule} onChange={setRule} />
          </>
        )}
        <TextField label="Notas" value={notes} placeholder="Opcional" onChange={setNotes} />
        {task && (
          <Button variant="destructive" icon="trash" block onClick={() => setDeleting(true)}>
            Borrar tarea
          </Button>
        )}
        <Problem error={error} />
      </div>
    </Sheet>
  );
}
