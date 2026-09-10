from __future__ import annotations

import pytest
from rich.cells import cell_len

from rpoker.domain.cards import STANDARD_52
from rpoker.ui.cards import MINI, STANDARD, WIDE, card_lines, parse_card
from rpoker.ui.tokens import THEMES

THEME = THEMES["onedark"]
SIZES = {"wide": WIDE, "standard": STANDARD, "mini": MINI}
STATES = ["normal", "dim", "winning", "hidden"]


@pytest.fixture(params=list(SIZES), ids=list(SIZES))
def size(request: pytest.FixtureRequest) -> tuple[int, int]:
    return SIZES[request.param]


@pytest.fixture(params=STATES)
def state(request: pytest.FixtureRequest) -> str:
    return request.param


def test_card_ladder_exact_dimensions(size: tuple[int, int], state: str) -> None:
    width, height = size
    for card in STANDARD_52:
        lines = card_lines(card, size, THEME, state)
        assert len(lines) == height
        for line in lines:
            assert cell_len(line.plain) == width


def test_hidden_card_matches_ladder(size: tuple[int, int]) -> None:
    width, height = size
    lines = card_lines(None, size, THEME)
    assert len(lines) == height
    assert all(cell_len(line.plain) == width for line in lines)
    assert all("░" in line.plain or "▒" in line.plain or "▓" in line.plain for line in lines[1:-1])


def test_face_rows_contain_rank_and_suit() -> None:
    ace = card_lines(parse_card("A♠"), WIDE, THEME)
    assert "A♠" in ace[1].plain
    assert ace[-2].plain.rstrip("│").endswith("A")
    ten = card_lines(parse_card("10♥"), WIDE, THEME)
    assert "10♥" in ten[1].plain
    assert ten[-2].plain.rstrip("│").endswith("10")


def test_pip_layout_places_expected_pips() -> None:
    deuce = card_lines(parse_card("2♣"), WIDE, THEME)
    pips = sum(line.plain.count("♣") for line in deuce[1:-1])
    assert pips == 3  # corner label + 2 pips
    ten = card_lines(parse_card("10♦"), WIDE, THEME)
    pips = sum(line.plain.count("♦") for line in ten[1:-1])
    assert pips == 11  # corner label + 10 pips


def test_parse_card_round_trip() -> None:
    for card in STANDARD_52:
        assert parse_card(str(card)) == card
