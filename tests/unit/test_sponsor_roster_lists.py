"""Sponsor extraction from plural roster lists.

Widely cosponsored bills name the chamber once and then list bare surnames:

    Cosponsored by Representative CARLOW of Buxton and
    Senators: BAILEY of York, BALDACCI of Penobscot, ...

Every pattern that needs a title adjoining the name collects only the few
entries carrying their own (President, Speaker), so a 99-cosponsor bill yielded
2 sponsors. A bare-name sweep existed until 300cd207 removed it for matching any
"Capitalized of Somewhere" in the block; this replacement is anchored to the
plural label, which bounds the search and supplies the chamber.

The fixtures below are the real opening text of the two worst cases found in the
published dataset, session 131 LD 1817 (96 stored sponsors) and LD 2007 (99).
"""

from maine_bills.text_extractor import TextExtractor

LD_1817 = (
    "Presented by Senator BRENNER of Cumberland.\n"
    "Cosponsored by Representative CARLOW of Buxton and\n"
    "Senators: BAILEY of York, BALDACCI of Penobscot, BEEBE-CENTER of Knox, "
    "BENNETT of Oxford, BLACK of Franklin, BRAKEY of Androscoggin, "
    "CARNEY of Cumberland, CHIPMAN of Cumberland, CURRY of Waldo, "
    "DAUGHTRY of Cumberland, DUSON of Cumberland, FARRIN of Somerset, "
    "GROHOSKI of Hancock, GUERIN of Penobscot, HARRINGTON of York, "
    "HICKMAN of Kennebec, INGWERSEN of York, President JACKSON of Aroostook, "
    "KEIM of Oxford, LaFOUNTAIN of Kennebec, LAWRENCE of York, "
    "LIBBY of Cumberland, LYFORD of Penobscot.\n"
    "Be it enacted by the People of the State of Maine as follows:\n"
)

LD_2007 = (
    "Presented by Speaker TALBOT ROSS of Portland.\n"
    "Cosponsored by President JACKSON of Aroostook and\n"
    "Representatives: ABDI of Lewiston, ANDREWS of Paris, ANKELES of Brunswick, "
    "ARFORD of Brunswick, BABIN of Fort Fairfield, BELL of Yarmouth, "
    "BOYER of Poland, BOYLE of Gorham, BRENNAN of Portland, "
    "CARMICHAEL of Greenbush, CLOUTIER of Lewiston, CLUCHEY of Bowdoinham, "
    "COLLINGS of Portland, COPELAND of Saco, CRAFTS of Newcastle, "
    "CRAVEN of Lewiston, CROCKETT of Portland, DANA of the Passamaquoddy Tribe, "
    "DHALAC of South Portland, DILL of Old Town, DODGE of Belfast, "
    "DOUDERA of Camden, EATON of Deer Isle.\n"
    "Be it enacted by the People of the State of Maine as follows:\n"
)


def names(text):
    return TextExtractor._extract_sponsors(text)


def mentions(text):
    return dict(TextExtractor._extract_sponsor_mentions(text))


# --- the regression itself ---


def test_roster_list_yields_every_cosponsor():
    """Before the fix this returned 3: BRENNER, CARLOW, JACKSON."""
    result = names(LD_1817)
    assert len(result) == 25
    assert result[0] == "BRENNER"  # presenter stays first
    for expected in ("BAILEY", "BALDACCI", "LYFORD", "KEIM", "CURRY"):
        assert expected in result


def test_house_roster_list_yields_every_cosponsor():
    result = names(LD_2007)
    assert len(result) == 25
    for expected in ("ABDI", "EATON", "CROCKETT", "BABIN"):
        assert expected in result


# --- chamber comes from the plural label ---


def test_bare_names_take_the_chamber_of_their_label():
    by_name = mentions(LD_1817)
    assert by_name["BAILEY"] == "Senate"
    assert by_name["LYFORD"] == "Senate"
    assert by_name["CARLOW"] == "House"  # own title, outside the roster list


def test_house_label_assigns_house():
    by_name = mentions(LD_2007)
    assert by_name["ABDI"] == "House"
    assert by_name["DHALAC"] == "House"


def test_individual_title_inside_a_list_wins_over_the_label():
    """President JACKSON sits inside "Senators:" and is a senator either way."""
    assert mentions(LD_1817)["JACKSON"] == "Senate"


def test_both_labels_in_one_block_split_correctly():
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Senators: BAILEY of York, CURRY of Waldo, "
        "Representatives: ABDI of Lewiston, BOYLE of Gorham.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    by_name = mentions(text)
    assert by_name["BAILEY"] == "Senate"
    assert by_name["CURRY"] == "Senate"
    assert by_name["ABDI"] == "House"
    assert by_name["BOYLE"] == "House"


# --- name shapes that appear in real rosters ---


def test_hyphenated_and_mixed_case_surnames_survive():
    result = names(LD_1817)
    assert "BEEBE-CENTER" in result
    assert "LaFOUNTAIN" in result


def test_two_word_surname_in_a_roster_list():
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Representatives: TALBOT ROSS of Portland, ABDI of Lewiston.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    assert "TALBOT ROSS" in names(text)


def test_tribal_representative_locality():
    assert "DANA" in names(LD_2007)


# --- the garbage that got the old sweep removed ---


def test_body_text_after_the_block_is_not_swept():
    text = LD_1817 + (
        "Sec. 1.  5 MRSA is amended to read: the Town of Brunswick and the "
        "University of Maine and Senator SOMEONE of Nowhere shall confer.\n"
    )
    result = names(text)
    assert "SOMEONE" not in result
    assert "Brunswick" not in result
    assert "University" not in result


def test_a_block_with_no_roster_label_is_unchanged():
    """The common case: a few cosponsors, each with its own title."""
    text = (
        "Presented by Senator DAUGHTRY of Cumberland.\n"
        "Cosponsored by Representative PERRY of Calais and "
        "Senator PERRY of Bangor.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    assert TextExtractor._extract_sponsor_mentions(text) == [
        ("DAUGHTRY", "Senate"),
        ("PERRY", "House"),
        ("PERRY", "Senate"),
    ]


def test_locality_is_required_for_a_roster_entry():
    """Without " of <place>" an entry is prose, not a sponsor."""
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Senators: BAILEY of York, And Other Things Happened.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    result = names(text)
    assert "BAILEY" in result
    assert not any(n.startswith("And") for n in result)


# --- the window, which truncated long lists on its own ---


def test_long_roster_survives_the_search_window():
    """A 99-cosponsor block runs past the old 2,500-character window.

    Entry lengths matter here, so they are kept realistic — Maine entries
    average about 30 characters ("BEEBE-CENTER of Knox, ",
    "DANA of the Passamaquoddy Tribe, "). At 2,500 this fixture yields 65 of
    100; the shortened localities an earlier draft used fit inside the old
    window and quietly tested nothing.
    """
    surnames = [f"MEMBER{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(99)]
    entries = ", ".join(f"{s} of South Cumberland Falls" for s in surnames)
    text = (
        "Legislative Document\nNo. 2007\nH.P. 1289\n"
        "House of Representatives, June 12, 2023\n"
        "An Act to Make Sure That Everything Is Properly Considered\n"
        "Presented by Speaker TALBOT ROSS of Portland.\n"
        f"Cosponsored by Representatives: {entries}.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    assert len(text) > 3500, "fixture must exceed the old window to be a guard"

    result = names(text)
    assert surnames[0] in result
    assert surnames[-1] in result, "tail of a long roster was truncated"
    assert len(result) == 100


def test_dedup_still_collapses_a_repeated_name():
    text = (
        "Presented by Senator BAILEY of York.\n"
        "Cosponsored by Senators: BAILEY of York, CURRY of Waldo.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    assert names(text) == ["BAILEY", "CURRY"]


# --- the sweep must not depend on the terminator list being exhaustive ---
#
# Review finding on #16: anchoring to the plural label is not by itself what
# bounds the sweep — the block terminators are, and they are a denylist with
# reachable gaps. `is_valid_name` is a 34-word denylist that omits City,
# Village, Board, University, Nation, Region: the vocabulary of bill body text.


def test_amendment_body_is_not_swept_for_sponsors():
    """Amendments open "Amend the bill", which no terminator matched, so the
    block ran the full window into body text. ~45% of a session's documents."""
    text = (
        "Presented by Representative ABDI of Lewiston.\n"
        "Cosponsored by Representatives: BOYLE of Gorham, CRAVEN of Lewiston.\n"
        "Amend the bill in section 1 by inserting: This applies to the "
        "City of Portland, Village of Kingfield, and the Board of Trustees of "
        "the University of Maine System.\n"
    )
    assert names(text) == ["ABDI", "BOYLE", "CRAVEN"]


def test_uppercase_resolved_terminates_the_block():
    """Resolutions print RESOLVED:; the terminator was case-sensitive."""
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Senators: BAILEY of York, CURRY of Waldo.\n"
        "RESOLVED: That we recognize the Penobscot Nation of Indian Island "
        "and the City of Bangor.\n"
    )
    assert names(text) == ["BRENNER", "BAILEY", "CURRY"]


def test_title_case_nouns_are_rejected_even_in_an_unterminated_block():
    """The guard that actually holds: rosters print surnames in capitals, and
    every false positive is Title Case. This block never terminates at all."""
    filler = "The department shall consider each application on its merits. " * 60
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Senators: BAILEY of York.\n"
        + filler
        + "reports from the Region of Downeast Maine, the Coalition of Towns, "
        "and the Friends of Acadia.\n"
    )
    assert names(text) == ["BRENNER", "BAILEY"]


def test_a_stray_plural_label_in_body_text_opens_no_segment_of_substance():
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Senators: BAILEY of York.\n"
        "Amend the bill by inserting: the panel consists of the following "
        "Representatives: Jane of Portland, John of Bangor.\n"
    )
    assert names(text) == ["BRENNER", "BAILEY"]


def test_all_real_surname_shapes_survive_the_capitals_guard():
    """Guard must not cost legitimate names: hyphenated, mixed-case, two-word,
    and leadership titles inside a list."""
    text = (
        "Presented by Senator BRENNER of Cumberland.\n"
        "Cosponsored by Senators: BEEBE-CENTER of Knox, LaFOUNTAIN of Kennebec, "
        "President JACKSON of Aroostook, "
        "Representatives: TALBOT ROSS of Portland, DHALAC of South Portland, "
        "DANA of the Passamaquoddy Tribe.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    assert names(text) == [
        "BRENNER",
        "JACKSON",
        "BEEBE-CENTER",
        "LaFOUNTAIN",
        "TALBOT ROSS",
        "DHALAC",
        "DANA",
    ]
