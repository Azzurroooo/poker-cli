from __future__ import annotations

import json
import random

import pytest

from rpoker.domain.actions import Action
from rpoker.domain.views import Street
from rpoker.engine.table import Table
from rpoker.net.codec import ProtocolError, decode, encode
from rpoker.net.messages import Act, Chat, Error, Hello, Result, State, Welcome


def make_messages() -> list:
    table = Table(["A", "B", "C"], [1000] * 3, (5, 10), random.Random(1))
    table.start_hand()
    result = Result(table.hand_result or _fake_result())
    welcome = Welcome(2, "测试房", ["A", "B", "C"], [5, 10], 1000, 30.0)
    return [
        Hello("小明"),
        welcome,
        Act("raise", 120),
        Act("fold"),
        Chat("你好", "小明"),
        State(table.seat_view(1)),
        result,
        Error("table_full"),
    ]


def _fake_result():
    table = Table(["A", "B"], [100, 100], (5, 10), random.Random(2))
    table.start_hand()
    while table.street is not Street.HAND_OVER:
        if table.to_act is None:
            table.advance_street()
        else:
            legal = table.seat_view(table.to_act).legal
            table.apply(table.to_act, Action("call") if not legal.can_check else Action("check"))
    assert table.hand_result is not None
    return table.hand_result


@pytest.mark.parametrize("message", make_messages())
def test_roundtrip(message):
    assert decode(encode(message)) == message


def test_encoding_is_single_json_line():
    line = encode(Hello("名字 ♠"))
    assert line.endswith(b"\n")
    json.loads(line)


def test_rejects_garbage():
    with pytest.raises(ProtocolError):
        decode(b"not json")
    with pytest.raises(ProtocolError):
        decode(b"[]")
    with pytest.raises(ProtocolError):
        decode(json.dumps({"type": "nope"}).encode())
    with pytest.raises(ProtocolError):
        decode(json.dumps({"type": "hello", "v": 99, "name": "x"}).encode())
    with pytest.raises(ProtocolError):
        decode(json.dumps({"type": "hello", "v": 1, "name": 5}).encode())
    with pytest.raises(ProtocolError):
        decode(json.dumps({"type": "state", "view": {"street": "flop", "hand_no": "x"}}).encode())
