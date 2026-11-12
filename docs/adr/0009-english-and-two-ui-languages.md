# ADR-0009: English everywhere, English and Spanish in the UI

Status: accepted

Code, identifiers, routes, comments, logs, errors, tool descriptions, prompts, docs and ADRs are
English. The UI ships in English and Spanish through message catalogs (`i18n/en.json`,
`i18n/es.json`), with English as the source language and a parity test. Each person picks their
language; the gateway passes it to every service with the rest of their preferences.

`tests/test_no_spanish.py` keeps Spanish out of everything else, with an explicit allowlist for data
that is Spanish by nature (a Spanish city's search terms, a Spanish bank's patterns). Comments are
kept to the minimum: what the code cannot say.
