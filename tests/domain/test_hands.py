from rpoker.domain.cards import Card, HandKind, find_best_hand
from tests.engine.helpers import card, cards


def kind_of(specs: str) -> HandKind:
    return find_best_hand(cards(specs)).kind


def test_high_card():
    score = find_best_hand(cards("As Kd 9c 7h 3s 2c 4d"))
    assert score.kind is HandKind.HIGH_CARD
    assert score.tiebreak == (14, 13, 9, 7, 4)


def test_pair():
    assert kind_of("As Ad 9d 7c 3s 2c 4d") is HandKind.PAIR


def test_two_pair():
    assert kind_of("As Ad 9d 9c 3s 2c 4d") is HandKind.TWO_PAIR


def test_trips():
    assert kind_of("As Ad Ac 7c 3s 2c 4d") is HandKind.TRIPS


def test_straight():
    assert kind_of("As Kd Qc Jh Td 2c 4d") is HandKind.STRAIGHT


def test_wheel_straight():
    score = find_best_hand(cards("As 2d 3c 4h 5d Kc Qd"))
    assert score.kind is HandKind.STRAIGHT
    assert score.tiebreak == (5,)


def test_flush():
    assert kind_of("As Ts 7s 4s 2s 3c Kd") is HandKind.FLUSH


def test_full_house():
    assert kind_of("As Ad Ac Kd Kh 2c 4d") is HandKind.FULL_HOUSE


def test_double_trips_plays_as_full_house():
    assert kind_of("As Ad Ac Kd Kh Kc 2d") is HandKind.FULL_HOUSE


def test_quads():
    assert kind_of("As Ad Ac Ah Kd 2c 4d") is HandKind.QUADS


def test_straight_flush():
    assert kind_of("As Ks Qs Js Ts 2c 4d") is HandKind.STRAIGHT_FLUSH


def test_wheel_straight_flush():
    score = find_best_hand(cards("As 2s 3s 4s 5s Kc Qd"))
    assert score.kind is HandKind.STRAIGHT_FLUSH
    assert score.tiebreak == (5,)


def test_royal_label():
    score = find_best_hand(cards("As Ks Qs Js Ts 2c 4d"))
    assert score.label() == "皇家同花顺"


def test_low_pair_with_big_kickers_loses_to_high_pair():
    low_pair_big_kickers = find_best_hand(cards("2c 2d Ac Kc Qc 7d 8h"))
    high_pair_weak_kickers = find_best_hand(cards("Kc Kd 9c 8c 7c 2d 3h"))
    assert high_pair_weak_kickers > low_pair_big_kickers


def test_two_pair_kicker_breaks_tie():
    assert find_best_hand(cards("As Ac 9d 9c Kd 2c 3h")) > find_best_hand(cards("As Ac 9d 9c Qd 2c 3h"))


def test_flush_compares_all_five_descending():
    assert find_best_hand(cards("As Ts 7s 4s 2s 3c Kd")) > find_best_hand(cards("As 9s 7s 4s 2s 3c Kd"))


def test_wheel_loses_to_six_high_straight():
    wheel = find_best_hand(cards("As 2d 3c 4h 5d Kc Qd"))
    six_high = find_best_hand(cards("2c 3d 4c 5h 6d Kc Qd"))
    assert six_high > wheel


def test_straight_ace_high_beats_king_high():
    ace_high = find_best_hand(cards("As Kd Qc Jh Td 2c 4d"))
    king_high = find_best_hand(cards("Ks Qd Jc Th 9d 2c 4d"))
    assert ace_high > king_high


def test_quads_kicker_breaks_tie():
    assert find_best_hand(cards("9s 9d 9c 9h Ac 2c 3h")) > find_best_hand(cards("9s 9d 9c 9h Kc 2c 3h"))


def test_pair_kicker_chain():
    kickers_a = find_best_hand(cards("5c 5d Ah Kc Qc 7d 8h"))
    kickers_b = find_best_hand(cards("5c 5d Ah Kc Jc 7d 8h"))
    assert kickers_a > kickers_b


def test_five_card_input_only():
    score = find_best_hand(cards("As Kd Qc Jh Td"))
    assert score.kind is HandKind.STRAIGHT
    assert isinstance(card("2c"), Card)
