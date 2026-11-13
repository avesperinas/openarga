from library.genre import propose


def test_the_subjects_propose_a_genre_from_the_most_specific() -> None:
    assert propose(["Fiction", "Magic realism"]) == "novel"
    assert propose(["Science fiction", "Fiction"]) == "fantasy_scifi"
    assert propose(["Detective and mystery stories"]) == "crime"
    assert propose(["Historical fiction"]) == "novel"
    assert propose(["Business history"]) == "business"
    assert propose(["Biograf\N{LATIN SMALL LETTER I WITH ACUTE}a"]) == "biography"
    assert propose(["Graphic novels"]) == "comic"
    assert propose(["Physics", "Cosmology"]) == "science"
    assert propose(["Spain -- History"]) == "history"
    assert propose(["Filosof\N{LATIN SMALL LETTER I WITH ACUTE}a"]) == "essay"
    assert propose([]) == "other"
