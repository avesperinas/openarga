# Notes (Notebook)

Your notes, linked. A note is a Markdown file with its title, in a folder, and its whole text,
frontmatter included, is what is stored: the same file opens in Obsidian. Notebook also keeps a
note for each thing in the other apps (a **card**) and a block per day in the daily note, so the
notes are where everything meets.

Module id `notebook`, schema `notebook`, role `mod_notebook`. Code in
[`modules/notebook`](../../modules/notebook), manifest in
[`manifest.yaml`](../../modules/notebook/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/notebook/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/notebook/` or `/notebook/graph` | The graph of notes and their links, with a highlight filter |
| `/notebook/notes` | The tree of folders and notes |
| `/notebook/note/<id>` | One note: read, edit, its properties, backlinks, and a side panel with its outline, links, local graph and history |
| `/notebook/today` | Today's note in the journal folder, created when opened |
| `/notebook/search?q=&tag=` | Full-text search, ignoring accents, umlauts and case |
| `/notebook/review` | The notes whose review date is today or earlier |
| `/notebook/trash` | Deleted notes, to restore or delete forever |
| `/notebook/import` | Importing an Obsidian vault from a `.zip` |
| `/notebook/settings` | The journal folder, the review property and the copy on GitHub |

The old Spanish paths (`/notebook/nota/<id>`, `/hoy`, `/repasar`...) still open their screen.
`⌘K` opens the command palette and `⌘O` jumps to a note.

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale.
Server texts that reach the person (widgets, the home panel, search details) come from
`src/notebook/i18n/{en,es}.json`. "Today", the journal and the digest follow the person's time
zone.

## Notes, links and history

- Links are `[[title]]`, `[[folder/title]]`, `[[title#heading]]` and `[[title|text]]`; a link
  to a note that does not exist yet waits for it. Moving or renaming a note rewrites the links that
  would stop finding it.
- Every change keeps the previous version. What Claude changes is marked as its own and can be
  undone in one step; any version can be restored from the history.
- The app saves with the version it read: if the note changed in between (Claude wrote to it), it
  says so and lets you keep yours or theirs.
- Images live next to the notes and are served by name, as in Obsidian.

## What other apps write

Apps publish **records** (`record` contract). Each record becomes a card in the app's folder, with
`arga` (its link, `library:<id>`) and `type` (`Book`) in its properties, and a day record goes into
that day's note, one section per app, with its figures as properties (`steps`, `kcal`). The app's
part is the block between `%% arga %%` and `%% /arga %%` and its properties: it is rebuilt when the
app changes it, and neither the editor nor Claude can change it. What the person writes outside
the block is theirs.

A link to something in an app, `[[library:<id>|text]]`, opens its card. When a note links to
something in another app, Notebook tells that app (`notebook.mention`), so it can show the note.

## Digest

Every week, month and quarter, Notebook writes a note in `Journal/Weeks`, `Journal/Months` and
`Journal/Quarters` (`2026-W41`, `2026-09`, `2026-Q4`): each app's figures (`metric` contract)
against the period before, what happened by name, what an app told of the week (a record with a
`week` property), and the goals (records of kind `Goal`). The week closes at six in the morning on
Monday in the person's zone, and a notification says it is ready. The quarter note is written once,
with a few questions per open goal for the person to answer.

## Review

When a date property is chosen in the settings (`next_review`, for instance), the notes whose date
is today or earlier show in Review and in its widget.

## Import and copy

- **Import**: a vault `.zip` is read in the browser, which shows what gets in, which links find
  nothing and what is left out, and where each top folder lands, before saving anything. Importing
  again fills notes that arrived empty and leaves the others alone.
- **Copy on GitHub**: with a GitHub connection in Hub (Notes → GitHub), every change is pushed to
  a private repository as `.md` files (`notes.push`), at most every ten minutes.

## Tools

Read (`notebook:read`): `search_notes`, `read_note`, `explore_graph`, `list_folder`,
`get_digest`. Write (`notebook:write`): `create_note`, `append_to_note`, `edit_note`,
`replace_section`, `set_properties`, `add_to_daily_note`, `move_note`. Their descriptions are in
the [manifest](../../modules/notebook/manifest.yaml). Claude does not delete notes.

## What it shares with other apps

- **Capabilities**: `notes.list`, `notes.read`, `notes.create`, `notes.write` and `notes.trash`,
  for apps that keep their own notes here (Study does).
- **Receives**: `record` (cards and daily notes), `metric` (the digest) and `linkable` (what the
  editor offers when linking to an app).
- **Home**: widgets for recent notes, today's note and what to review, and a panel.

## Demo

[`src/notebook/demo.py`](../../modules/notebook/src/notebook/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): a few linked notes in folders, a week of journal
entries and the review property, with one note due. Dates are relative to today. It can run any
number of times.
