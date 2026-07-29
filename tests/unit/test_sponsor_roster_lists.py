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


# --- second review round: bounding the sweep positively ---
#
# The reviewer's point was that anchoring to the plural label does not bound the
# sweep; only the terminators do, and those are a denylist with reachable gaps.
# The fix is to make the roster a bounded positive parse: a contiguous
# comma-delimited run of "NAME of LOCALITY" cells, ended by the first cell that
# is not one.


def test_an_amendment_directive_terminates_the_block():
    """Amendments open "Amend the bill/resolve/amendment by", which was not in
    the terminator list -- so on an amendment the block ran to the window edge."""
    for directive in ("Amend the bill", "Amend the resolve", "Amend the amendment"):
        text = (
            "Cosponsored by Representatives: ABDI of Lewiston, BOYLE of Gorham.\n"
            f"{directive} by inserting after section 1 the following: "
            "the LURC of Augusta shall report.\n"
        )
        assert names(text) == ["ABDI", "BOYLE"], directive


def test_a_lettered_section_terminates_the_block():
    """Terminator was Sec.\\s*\\d, so the lettered form "Sec. A-1" slipped past."""
    text = (
        "Cosponsored by Senators: BRENNER of Cumberland, BAILEY of York.\n"
        "Sec. A-1. 5 MRSA 12004 is amended. The Board of Trustees of Orono "
        "and the Council of Elders of Indian Township shall meet.\n"
    )
    assert names(text) == ["BRENNER", "BAILEY"]


def test_a_prose_cosponsored_by_does_not_open_a_block():
    """Case-insensitivity belongs on the terminators, not the opener. Applied to
    the whole pattern it let a lowercase "cosponsored by" inside the window open
    a block where the bill had none."""
    text = (
        "Be it enacted by the People of the State of Maine as follows:\n"
        "The report shall list each measure cosponsored by Senators: "
        "BRENNER of Cumberland, GRANT of Gardiner.\n"
    )
    assert names(text) == []


def test_a_cell_that_is_not_a_clean_entry_ends_the_roster():
    """Skipping bad cells (continue) let body text far past the end of the
    roster still be harvested, because prose always intervenes and was simply
    stepped over. The first bad cell must end the run."""
    text = (
        "Cosponsored by Senators: BAILEY of York, CURRY of Waldo, "
        "and the department shall report to the joint standing committee, "
        "MARTIN of Eagle Lake.\n"
    )
    assert names(text) == ["BAILEY", "CURRY"]
    assert "MARTIN" not in names(text)


def test_a_long_roster_is_not_truncated_by_the_entry_guard():
    """The guard must not cost a widely cosponsored bill its list -- recovering
    those was the entire point of the change."""
    roster = ", ".join(f"NAME{c} of Town" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    # Real rosters print surnames in capitals with no digits; this stands in for
    # a 26-name list without inventing 26 plausible Maine surnames.
    roster = roster.replace("NAME", "SMYTH").replace("0", "")
    text = f"Cosponsored by Senators: {roster}.\nBe it enacted:\n"
    assert len(names(text)) == 26


def test_an_agency_acronym_inside_the_roster_run_is_not_separable_by_shape():
    """Known limit, recorded deliberately rather than papered over.

    "DHHS of Augusta" is grammatically identical to "BAILEY of York" -- same
    capitals, same "of LOCALITY". No shape test can separate them, so a cell
    like this, appearing *inside* an unterminated roster run, is read as a name.

    What bounds it in practice is that real bill text following a roster starts
    with a terminator (the enacting clause, a preamble, a section, an amendment
    directive), and the sweep stops there. The corpus audit
    (scripts/audit_roster_sweep.py) measures whether that holds.

    The downstream defence is enrichment: an unmatched name publishes with a
    null sponsor_id and null confidence rather than a guessed identity, so a
    stray acronym is visible in the data rather than silently wrong.
    """
    text = (
        "Cosponsored by Senators: BAILEY of York, DHHS of Augusta.\n"
        "Be it enacted by the People of the State of Maine as follows:\n"
    )
    assert names(text) == ["BAILEY", "DHHS"]


# --- round 3: each guard isolated, so removing it turns a test red ---
#
# The tests above were written to lock in specific guards and did not: the
# prefix-parse change subsumed them, so deleting the capitals guard, the
# `Amend the ...` terminator, the lettered-section terminator, or the
# prefix-branch stop left the whole suite green. Each fixture below is built so
# that ONE guard is the only thing between the parser and a bad capture.


def test_the_capitals_guard_is_load_bearing():
    """Isolates _ROSTER_SURNAME.

    The noun has to be Title Case (so the capitals guard is what rejects it) and
    NOT on the denylist (so is_valid_name is not what rejects it) -- otherwise
    the fixture passes with the capitals guard deleted and proves nothing.
    """
    text = (
        "Cosponsored by Senators: BAILEY of York, Meadow of Islesboro, Harbor of Cutler.\n"
        "The department shall consider each application on its merits.\n"
    )
    assert names(text) == ["BAILEY"]


def test_the_denylist_is_load_bearing_in_capitals():
    """Isolates is_valid_name on the roster path, which is ALL CAPS by
    construction. The list is written in Title Case and was compared
    case-sensitively, so every word on it passed in capitals -- COUNTY,
    DEPARTMENT, SENATE and LEGISLATURE were all reachable as "sponsors" while
    the list that names them looked like it was doing the work."""
    for noun in ("COUNTY", "DEPARTMENT", "SENATE", "LEGISLATURE", "CITY", "UNIVERSITY"):
        text = f"Cosponsored by Senators: BAILEY of York, {noun} of Cumberland.\nBe it enacted:\n"
        assert names(text) == ["BAILEY"], noun


def test_the_amend_terminator_is_load_bearing():
    """Isolates `Amend the (bill|resolve|amendment)`.

    The bad text has to sit behind a SECOND plural label. _roster_segments
    splits the block on those labels and each segment starts a fresh run, so a
    label after the directive is reachable even though the prose before it
    would have stopped the first run. Without the terminator the block extends
    to include that second label; with it, the block is cut first.
    """
    for directive in ("Amend the bill", "Amend the resolve", "Amend the amendment"):
        text = (
            f"Cosponsored by Representatives: ABDI of Lewiston, BOYLE of Gorham. "
            f"{directive} by adding, Senators: MARTIN of Eagle Lake, GRANT of Gardiner.\n"
        )
        assert names(text) == ["ABDI", "BOYLE"], directive


def test_the_lettered_section_terminator_is_load_bearing():
    """Isolates `Sec.\\s*[A-Za-z0-9]`; same construction as above, since the
    digits-only form let the block run past `Sec. A-1` into the body."""
    text = (
        "Cosponsored by Senators: BRENNER of Cumberland, BAILEY of York. "
        "Sec. A-1. 5 MRSA 12004 is amended by adding, "
        "Representatives: MARTIN of Eagle Lake, GRANT of Gardiner.\n"
    )
    assert names(text) == ["BRENNER", "BAILEY"]


def test_the_prefix_branch_stops_the_run():
    """Isolates the `return` after a partially-consumed cell. With `continue`
    the run steps over the prose and keeps harvesting the cells behind it."""
    text = (
        "Cosponsored by Senators: BAILEY of York. The department shall report, "
        "MARTIN of Eagle Lake, GRANT of Gardiner.\n"
    )
    assert names(text) == ["BAILEY"]


def test_a_locality_must_end_the_cell_not_run_into_a_clause():
    """A roster cell is a noun phrase; "MDOT of Augusta shall study the matter"
    is a clause. Both fit the four-word ceiling, so the sentence boundary is
    what separates them."""
    for clause in (
        "MDOT of Augusta shall study the matter.",
        "MRSA of Title 5 is amended to read as follows.",
        "PART A of Chapter 12 takes effect on July 1.",
    ):
        text = f"Cosponsored by Senators: BAILEY of York, {clause}\n"
        assert names(text) == ["BAILEY"], clause


def test_a_short_clause_that_reads_as_a_locality_is_not_separable():
    """The other half of the known limit, recorded rather than asserted away.

    "USDA of Washington provides the funds." is a clause, but "Washington
    provides the funds" fits the four-word ceiling and ends in a period, so it
    is shape-identical to a long locality. The boundary closes clauses that run
    LONGER than a locality; it cannot close ones that do not.

    NOT bounded to one per segment — an earlier version of this docstring
    claimed that and it was false. A fully-consumed bogus cell leaves
    ``match.end() == len(cell)``, so the run CONTINUES and the next such cell is
    read too. What actually bounds it is that every cell in the run must keep
    fitting the shape, and that enrichment publishes an unmatched name with a
    null id and null confidence rather than a guessed identity.
    """
    text = "Cosponsored by Senators: BAILEY of York, USDA of Washington provides the funds.\n"
    assert names(text) == ["BAILEY", "USDA"]

    # Three, not one — the case the old docstring said could not happen.
    run_on = (
        "Cosponsored by Senators: BAILEY of York, DHHS of Augusta shall report, "
        "DOE of Portland shall assist, EPA of Maine is repealed.\n"
    )
    assert names(run_on) == ["BAILEY", "DHHS", "DOE", "EPA"]


def test_abbreviated_place_names_survive_the_sentence_boundary():
    """The period in "St. Albans" must not read as the end of the cell, or the
    roster stops one town early."""
    text = (
        "Cosponsored by Senators: SMYTH of St. Albans, PIERCE of St. George, "
        "JONES of Isle au Haut, DANA of the Passamaquoddy Tribe.\n"
        "Be it enacted:\n"
    )
    assert names(text) == ["SMYTH", "PIERCE", "JONES", "DANA"]


# --- round 4: losses measured against 296 real bills, sessions 125-132 ---


def test_a_singular_trailing_chamber_label_opens_a_segment():
    """Maine routinely closes a roster with a one-member label. Matching only
    the plural cost that entry AND terminated the run before it, since
    "Representative: STUCKEY of Portland" is not a well-formed cell. Largest
    single loss class in the corpus: 55 of 68 affected bills."""
    text = (
        "Cosponsored by Senators: FARNSWORTH of Cumberland, ALFOND of Cumberland, "
        "Representative: STUCKEY of Portland.\nBe it enacted:\n"
    )
    assert names(text) == ["FARNSWORTH", "ALFOND", "STUCKEY"]


def test_the_singular_label_still_carries_its_chamber():
    text = (
        "Cosponsored by Representatives: BERRY of Bowdoinham, "
        "Senator: BLACK of Franklin.\nBe it enacted:\n"
    )
    by_name = mentions(text)
    assert by_name["BERRY"] == "House"
    assert by_name["BLACK"] == "Senate"


def test_a_denylisted_name_does_not_take_the_rest_of_the_roster_with_it():
    """Session 129 HP0037, real text. "HALL of Wilton" is a real legislator who
    collides with the denylist; ending the run on a rejection took HICKMAN,
    INGWERSEN, MAXMIN, O'NEIL and BLACK down with him — six lost from one
    collision. A rejection skips the cell now; only a cell that is not an entry
    at all, or one with prose behind it, ends the run."""
    text = (
        "Cosponsored by Representatives: BERRY of Bowdoinham, DUNPHY of Old Town, "
        "HALL of Wilton, HICKMAN of Winthrop, INGWERSEN of Arundel, "
        "MAXMIN of Nobleboro, O'NEIL of Saco, Senator: BLACK of Franklin.\n"
        "Be it enacted:\n"
    )
    assert names(text) == [
        "BERRY",
        "DUNPHY",
        "HALL",
        "HICKMAN",
        "INGWERSEN",
        "MAXMIN",
        "O'NEIL",
        "BLACK",
    ]


def test_hall_is_a_surname_on_the_roster_path():
    """The denylist exists for the title-adjoining patterns, where "Hall" is
    "City Hall". Inside a chamber-anchored roster it is positionally a surname.
    This only became reachable when the denylist was case-folded."""
    text = "Cosponsored by Senators: HALL of Wilton, BAILEY of York.\nBe it enacted:\n"
    assert names(text) == ["HALL", "BAILEY"]


def test_a_denylisted_noun_is_still_dropped_just_not_cascading():
    text = (
        "Cosponsored by Senators: BAILEY of York, COUNTY of Cumberland, "
        "CURRY of Waldo.\nBe it enacted:\n"
    )
    assert names(text) == ["BAILEY", "CURRY"]


def test_tribal_designations_exceed_the_ordinary_locality_ceiling():
    """Session 127 HP0013, real text. "of the Houlton Band of Maliseet Indians"
    is five words; at a four-word ceiling the cell failed, and because it sorts
    first alphabetically the whole roster died — 0 of 8. The Maliseet seat was
    refilled in May 2025, so this is session 132 and in scope."""
    text = (
        "Cosponsored by Senator DILL of Penobscot and Representatives: "
        "BEAR of the Houlton Band of Maliseet Indians, BECK of Waterville, "
        "DANA of the Passamaquoddy Tribe, DION of Portland, MARTIN of Eagle Lake, "
        "ROTUNDO of Lewiston, SCHNECK of Bangor.\nBe it enacted:\n"
    )
    assert names(text) == [
        "DILL",
        "BEAR",
        "BECK",
        "DANA",
        "DION",
        "MARTIN",
        "ROTUNDO",
        "SCHNECK",
    ]


def test_the_longer_ceiling_is_gated_on_the_article():
    """The extra room is for "of THE <tribal designation>", which is what the
    long real localities look like. Ungated it re-accepts the clause class —
    "of Augusta shall study the matter" is five words too."""
    for clause in (
        "MDOT of Augusta shall study the matter.",
        "MRSA of Title 5 is amended to read as follows.",
        "PART A of Chapter 12 takes effect on July 1.",
    ):
        text = f"Cosponsored by Senators: BAILEY of York, {clause}\n"
        assert names(text) == ["BAILEY"], clause


# --- round 5: the prefix stop must survive a rejected name ---


def test_a_rejected_name_on_a_prose_cell_still_stops_the_run():
    """Ordering the guard rejection before the prefix-stop skipped that stop, so
    a rejected name on a cell with prose behind it let the run continue into
    body text — exactly what the stop exists to prevent. Zero occurrences in 271
    real bills, but the docstring claimed prose is never read."""
    text = (
        "Presented by Senator BAILEY of York.\n"
        "Cosponsored by Senators: DAUGHTRY of Cumberland, COUNTY of Cumberland. "
        "Notwithstanding any other provision of law, MDOT of Augusta, "
        "GROHOSKI of Hancock.\nBe it enacted:\n"
    )
    assert names(text) == ["BAILEY", "DAUGHTRY"]


def test_a_rejected_name_on_a_clean_cell_still_skips_rather_than_stops():
    """The other half: the non-cascading skip must survive the fix above."""
    text = (
        "Cosponsored by Senators: BAILEY of York, COUNTY of Cumberland, "
        "CURRY of Waldo.\nBe it enacted:\n"
    )
    assert names(text) == ["BAILEY", "CURRY"]


# --- guards the round-5 mutation pass found unconstrained ---


def test_the_label_requires_its_colon():
    """ "Senators" without a colon is prose, not a roster opener. Real rosters
    always carry it; dropping the requirement lets a bare plural in running
    text open a segment."""
    text = (
        "Cosponsored by Senator BAILEY of York and the Senators "
        "MARTIN of Eagle Lake, GRANT of Gardiner.\n"
    )
    assert names(text) == ["BAILEY"]


def test_the_label_is_word_bounded():
    """Without \\b the label matches as a substring and opens a bogus segment."""
    text = (
        "Cosponsored by Senator BAILEY of York. "
        "CoSenators: MARTIN of Eagle Lake, GRANT of Gardiner.\n"
    )
    assert names(text) == ["BAILEY"]


def test_an_individual_title_inside_a_roster_keeps_its_own_chamber():
    """A Speaker listed inside a "Senators:" run is still House.

    Note this is NOT isolating _ROSTER_ENTRY's title group: the title-adjoining
    patterns match "Speaker FECTEAU of Biddeford" independently, so the chamber
    is right either way and neutering the group changes nothing observable.
    Kept as a behavioural assertion, not claimed as a guard test.
    """
    text = (
        "Cosponsored by Senators: BAILEY of York, Speaker FECTEAU of Biddeford, "
        "CURRY of Waldo.\nBe it enacted:\n"
    )
    by_name = mentions(text)
    assert by_name["BAILEY"] == "Senate"
    assert by_name["FECTEAU"] == "House"
    assert by_name["CURRY"] == "Senate"


# --- issue #20: two real surname forms the sweep dropped ---
#
# Both were found by an independent review of #16 that ran the extractor over
# 296 real bills via getPDF.asp, and both were deferred from that PR because
# neither fix is a one-liner. Both cascade: the failing cell ends the run, so
# every cosponsor behind it is lost too, which is the actual cost.


def test_a_same_surname_disambiguator_is_part_of_the_name_not_a_cell_boundary():
    """Session 129 HP0006, real text. Maine distinguishes two sitting members
    who share a surname with a trailing initial. Splitting on every comma made
    the first cell just "SANBORN" — no locality, so not an entry at all — which
    ended the run and took VITELLI with it."""
    text = (
        "Cosponsored by Senators: SANBORN, H. of Cumberland, VITELLI of Sagadahoc.\n"
        "Be it enacted:\n"
    )
    assert names(text) == ["SANBORN, H.", "VITELLI"]


def test_the_disambiguator_is_kept_because_it_is_what_identifies_the_member():
    """Dropping it back to "SANBORN" would merge two different legislators, and
    the extracted string is supposed to be what the document says."""
    text = "Cosponsored by Senators: SANBORN, H. of Cumberland.\nBe it enacted:\n"
    assert names(text) == ["SANBORN, H."]


def test_both_members_of_a_shared_surname_survive_as_separate_sponsors():
    text = (
        "Cosponsored by Senators: SANBORN, H. of Cumberland, "
        "SANBORN, L. of Cumberland, VITELLI of Sagadahoc.\nBe it enacted:\n"
    )
    assert names(text) == ["SANBORN, H.", "SANBORN, L.", "VITELLI"]


def test_a_surname_with_a_lowercase_particle_is_a_name():
    """Session 125 HP0018, real text. The name group required every word
    capitalised and allowed at most two, so "CORNELL du HOUX" failed — and it
    is the FIRST cell, so all seven cosponsors were lost."""
    text = (
        "Cosponsored by Representatives: CORNELL du HOUX of Brunswick, "
        "BEAULIEU of Auburn, BOLAND of Sanford, CAIN of Orono, CHASE of China, "
        "DILL of Old Town, HUNT of Buxton.\nBe it enacted:\n"
    )
    assert names(text) == [
        "CORNELL du HOUX",
        "BEAULIEU",
        "BOLAND",
        "CAIN",
        "CHASE",
        "DILL",
        "HUNT",
    ]


def test_the_particle_rule_is_the_one_this_file_already_argues_for_localities():
    """text_extractor.py argues explicitly that localities must not require
    every word capitalised, because "Isle au Haut" has a lowercase particle —
    and then applied exactly that rule to surnames."""
    text = (
        "Cosponsored by Representatives: CORNELL du HOUX of Isle au Haut, "
        "CAIN of Orono.\nBe it enacted:\n"
    )
    assert names(text) == ["CORNELL du HOUX", "CAIN"]


# --- the widened patterns must not widen what they accept as a sponsor ---


def test_the_particle_arm_does_not_swallow_the_locality_separator():
    """A general "capital word, lowercase word, capital word" name could in
    principle consume the " of " that bounds the locality. It cannot, because
    the locality needs an " of " of its own."""
    text = "Cosponsored by Senators: BAILEY of York of Cumberland.\nBe it enacted:\n"
    assert names(text) == ["BAILEY"]


def test_the_particle_arm_does_not_re_open_the_clause_class():
    """The cases the locality boundary was added to reject must stay rejected
    now that the name may carry a lowercase middle word."""
    for clause in (
        "MDOT of Augusta shall study the matter.",
        "PART A of Chapter 12 takes effect on July 1.",
        "MRSA of Title 5 is amended to read as follows.",
    ):
        text = f"Cosponsored by Senators: BAILEY of York, {clause}\n"
        assert names(text) == ["BAILEY"], clause


def test_a_denylisted_noun_is_still_dropped_when_it_carries_a_particle():
    """Widening the arity ceiling to 3 must not let a denylisted word through
    on a longer name."""
    text = (
        "Cosponsored by Senators: BAILEY of York, BOARD of the City of Portland, "
        "CURRY of Waldo.\nBe it enacted:\n"
    )
    assert "BOARD" not in " ".join(names(text))
    assert names(text) == ["BAILEY", "CURRY"]


def test_the_disambiguator_lookahead_does_not_glue_ordinary_cells_together():
    """Only "<single capital>. of " is an internal comma. Everything else after
    a comma opens a new cell, including a name that merely starts with one."""
    text = (
        "Cosponsored by Senators: BAILEY of York, CURRY of Waldo, "
        "GROHOSKI of Hancock.\nBe it enacted:\n"
    )
    assert names(text) == ["BAILEY", "CURRY", "GROHOSKI"]


def test_a_trailing_initial_still_requires_its_locality():
    """The disambiguator is part of the name, not a substitute for the entry
    shape — a cell that stops at the initial is still not an entry."""
    text = "Cosponsored by Senators: BAILEY of York, SANBORN, H.\nBe it enacted:\n"
    assert names(text) == ["BAILEY"]
