# ADR-0007: App ids are English and never an event category

Status: accepted

An app's id is its schema, its role, its API prefix, its URL and the prefix of its tools and events.
Ids are short English nouns: `training`, `vitals`, `macros`, `recipes`, `shopping`, `money`, `goals`,
`outings`, `travel`, `library`, `planner`, `notebook`, `insights`, `study`, `hub`.

An id must never be one of the categories of outside data (`finance`, `health`, `calendar`, `books`,
`notes`, `food`, `places`, `weather`, `leisure`, `economy`, `ai`). An app publishes its own events as
`<id>.*`; if its id were a category, it could publish `finance.balance` as if it came from a bank.
That is why Finance is `money`, Health is `vitals`, Calendar is `planner`, Books is `library` and
Notes is `notebook`.

What people see is the app's name, which is translated and can be changed in Settings (name sets:
Standard, Arga, Greek gods, your own).
