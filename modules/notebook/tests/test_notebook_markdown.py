from __future__ import annotations

import unicodedata

import pytest

from notebook import markdown as md

NFD = unicodedata.normalize("NFD", "Präpositionen")


def test_a_name_from_icloud_is_the_same_name() -> None:
    assert NFD != "Präpositionen"
    assert md.key(NFD) == md.key("präpositionen")


@pytest.mark.parametrize("bad", ["a/b", "a:b", "a#b", "a|b", "[a]", "a^b", "", "   ", ".hidden"])
def test_a_title_that_would_break_a_link_is_refused(bad: str) -> None:
    with pytest.raises(md.InvalidName):
        md.title(bad)


def test_a_title_loses_its_md_and_its_spaces() -> None:
    assert md.title("  DE 2.3 Perfekt.md ") == "DE 2.3 Perfekt"


def test_a_folder_is_a_clean_path() -> None:
    assert md.folder("/Study//German/ B1 Gramatik /") == "Study/German/B1 Gramatik"
    assert md.folder("") == ""
    assert md.ancestors("a/b/c") == ["a", "a/b", "a/b/c"]
    with pytest.raises(md.InvalidName):
        md.folder("a/../b")


NOTE = """---
tags:
  - deutsch/b1
thema: Kasus
naechste_wiederholung: 2026-10-01
fehlerquote: 0.25
---
# Kasus

Siehe [[DE 1.2 Artikelwörter und Deklination]] und [[B1 Gramatik/DE 1.8 Genitiv|Genitiv]].

| Fall | Nota |
|---|---|
| Dativ | [[DE 4.1 Akkusativ- und Dativpräpositionen\\|Dativ]] |

```python
x = "[[not a link]]"  # nor #tag
```

Mit `[[neither]]` inline. ![[map.png]] and [[#Kasus]] and [[training:squat]].

#grammatik #2026 %% [[comment]] %%
"""


def test_properties_are_read_with_dates_as_text() -> None:
    assert md.properties(NOTE) == {
        "tags": ["deutsch/b1"],
        "thema": "Kasus",
        "naechste_wiederholung": "2026-10-01",
        "fehlerquote": 0.25,
    }


def test_links_outside_code_and_comments() -> None:
    found = md.links(NOTE)

    assert [(link.kind, link.target) for link in found] == [
        ("note", "DE 1.2 Artikelwörter und Deklination"),
        ("note", "B1 Gramatik/DE 1.8 Genitiv"),
        ("note", "DE 4.1 Akkusativ- und Dativpräpositionen"),
        ("file", "map.png"),
        ("app", "training:squat"),
    ]
    genitive = found[1]
    assert (genitive.title_key, genitive.folder_key, genitive.alias) == (
        "de 1.8 genitiv",
        "b1 gramatik",
        "Genitiv",
    )
    assert found[2].escaped_pipe and found[2].alias == "Dativ"
    assert found[3].embed
    assert found[0].line == 9


def test_a_link_in_nfd_has_the_same_key_as_the_note() -> None:
    (link,) = md.links(f"[[DE 4.2 Wechsel{NFD}]]")
    assert link.title_key == md.key("DE 4.2 Wechselpräpositionen")


def test_tags_from_text_and_properties_without_numbers_or_code() -> None:
    assert md.tags(NOTE) == ["grammatik", "deutsch/b1"]


def test_a_heading_is_not_a_tag_and_an_url_fragment_is_not_either() -> None:
    assert md.tags("# Titel\n\nhttps://x.de/#anker and [[Note#Part]]") == []


def test_rewriting_a_link_keeps_its_heading_alias_embed_and_escaped_pipe() -> None:
    text = "[[Alt#Teil|Alias]] | ![[Alt]] | [[Alt\\|x]] | [[Other]]"

    rewritten = md.rewrite_links(text, lambda link: "Neu" if link.title_key == "alt" else None)

    assert rewritten == "[[Neu#Teil|Alias]] | ![[Neu]] | [[Neu\\|x]] | [[Other]]"


def test_setting_properties_keeps_the_order_and_writes_dates_as_dates() -> None:
    changed = md.set_properties(NOTE, {"naechste_wiederholung": "2026-10-15", "status": "ok"}, [])

    assert changed.startswith(
        "---\ntags:\n  - deutsch/b1\nthema: Kasus\nnaechste_wiederholung: 2026-10-15\n"
        "fehlerquote: 0.25\nstatus: ok\n---\n# Kasus\n"
    )
    assert md.split(changed).body == md.split(NOTE).body


def test_removing_every_property_removes_the_frontmatter() -> None:
    assert md.set_properties("---\na: 1\n---\nTexto\n", {}, ["a"]) == "Texto\n"


def test_properties_are_added_to_a_note_without_them() -> None:
    assert md.set_properties("Texto\n", {"a": 1}, []) == "---\na: 1\n---\nTexto\n"


def test_broken_frontmatter_gives_no_properties_but_refuses_to_be_edited() -> None:
    broken = "---\na: [1\n---\nTexto"
    assert md.properties(broken) == {}
    with pytest.raises(md.InvalidProperties):
        md.set_properties(broken, {"b": 2}, [])


SECTIONS = """---
a: 1
---
# Kasus

Intro.

## Dativ

Dativ text.

### Detail

More.

## Genitiv

Genitiv text.
"""


def test_the_outline_skips_the_frontmatter() -> None:
    assert [(h.level, h.text, h.line) for h in md.headings(SECTIONS)] == [
        (1, "Kasus", 3),
        (2, "Dativ", 7),
        (3, "Detail", 11),
        (2, "Genitiv", 15),
    ]


def test_replacing_a_section_keeps_its_heading_and_the_next_one() -> None:
    changed = md.replace_section(SECTIONS, "## dativ", "New.")

    assert "## Dativ\nNew.\n\n## Genitiv\n" in changed
    assert "Detail" not in changed


def test_appending_under_a_heading_goes_before_the_next_one() -> None:
    changed = md.append(SECTIONS, "- point", "Dativ")

    assert "More.\n\n- point\n\n## Genitiv" in changed


def test_appending_at_the_end() -> None:
    assert md.append("Uno\n\n", "Dos") == "Uno\n\nDos\n"
    assert md.append("", "Dos") == "Dos\n"


def test_a_missing_or_repeated_heading_says_so() -> None:
    with pytest.raises(md.NotFoundInNote, match="The ones there are"):
        md.section(SECTIONS, "Akkusativ")
    with pytest.raises(md.Ambiguous):
        md.section("# A\n\n# A\n", "A")


def test_a_fragment_must_appear_exactly_once() -> None:
    assert md.replace_fragment("one two three", "two", "2") == "one 2 three"
    with pytest.raises(md.NotFoundInNote):
        md.replace_fragment("one", "two", "2")
    with pytest.raises(md.Ambiguous, match="2 times"):
        md.replace_fragment("two two", "two", "2")


def test_a_fragment_in_nfd_finds_the_same_text() -> None:
    assert md.replace_fragment("Präpositionen today", NFD, "X") == "X today"


def test_search_folds_accents_umlauts_and_eszett() -> None:
    assert md.fold("Präfix Straße Crème") == "prafix strasse creme"
    assert md.query_words("  Präfix, straße! ") == ["prafix", "strasse"]


def test_a_snippet_finds_the_word_with_its_original_letters() -> None:
    body = "x " * 200 + "Die Präposition steht vor dem Nomen." + " y" * 200

    found = md.snippet(body, "praposition", width=60)

    assert "Präposition" in found
    assert found.startswith("…") and found.endswith("…")


def test_a_word_also_finds_its_form_without_a_plural_ending() -> None:
    assert md.variants("gradientes") == ["gradientes", "gradient", "gradiente"]
    assert md.variants("dativ") == ["dativ"]
    assert md.tsquery("Präpositionen mit") == (
        "(prapositionen:* | praposition:* | prapositione:*) & (mit:*)"
    )
    assert md.tsquery("  ") is None


def test_an_excerpt_does_not_repeat_the_title() -> None:
    from notebook.service import without_title

    assert without_title("# DE 1.1 Kasus\n\nKern", "DE 1.1 Kasus") == "\nKern"
    assert without_title("# Other\nKern", "DE 1.1 Kasus") == "# Other\nKern"


def test_the_excerpt_of_a_list_reads_as_text() -> None:
    from notebook.service import plain

    body = (
        "Review for the **Goethe-Zertifikat B1**. Scope _B1+_.\n\n"
        "| Kasus | Frage |\n|---|---|\n| Nominativ | wer? |\n\n---\n\n"
        "> [!tip] Careful\n> after *sein* comes the `nominative`.\n\n"
        "```python\nprint(1)\n```\n- a snake_case"
    )

    assert plain(body) == (
        "Review for the Goethe-Zertifikat B1. Scope B1+. Careful after sein comes the "
        "nominative. a snake_case"
    )
