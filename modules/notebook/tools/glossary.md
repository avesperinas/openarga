# Notebook glossary

- **Note**: a Markdown file with its title, in a folder. Its whole text, frontmatter included, is
  what is stored: it is the same file as in Obsidian.
- **Title**: the file name without `.md`. Unique within its folder, ignoring case. It cannot contain
  `/ \ : [ ] # ^ |`.
- **Path**: `folder/subfolder/title`. Used to name a note when two in different folders share a
  title.
- **Link**: `[[title]]`, `[[folder/title]]`, `[[title#heading]]` or `[[title|text shown]]`. It
  reaches the note with that title; if there are several, the one in the same folder and then the
  one with the shortest path. A link to a note that does not exist yet is valid: it waits for it.
- **Backlink**: a note that links to this one.
- **Properties**: the YAML frontmatter between two `---` at the start. Dates are ISO.
- **Tag**: `#tag` in the text or in the `tags` property. `#a/b` is a child of `#a`, and searching
  by `a` finds both.
- **Section**: what is under a heading until the next heading of the same or a higher level, with
  its subsections.
- **Daily note**: the one named after the day, `2026-09-28`, in the journal folder.
- **History**: every change keeps how the note was. What Claude changes is marked as its own and
  can be undone in the app.
- **Trash**: where notes deleted in the app go. Claude does not delete.
- **Card**: the note of something in an arga app (a book in Library, a trip in Travel, an account
  in Money), in that app's folder. The app writes it and it is rebuilt when it changes there. It
  carries `arga` (its link, `library:<id>`) and `type` (`Book`) in its properties.
- **arga block**: what is between `%% arga %%` and `%% /arga %%` in a card or in a daily note. Its
  app writes it, as it does its properties: it is not changed in Notebook but with that app's
  tools. What is outside the block belongs to the person and no app touches it.
- **A day's things**: in the daily note, a block at the end with one section per app (the
  training, what was eaten, the spending, the classes) and its figures in the properties (`steps`,
  `kcal`, `spent_eur`). To answer "what did I do on Tuesday", read that day's note.
- **Link to something in an app**: `[[library:<id>|text]]`. It leads to its card if it has one.
