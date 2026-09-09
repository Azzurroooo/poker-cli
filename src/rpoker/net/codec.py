from __future__ import annotations

import json

from rpoker.domain.actions import LegalActions
from rpoker.domain.cards import Card, HandKind, HandScore, Suit
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.engine.table import Award, HandResult
from rpoker.net.messages import (
    PROTOCOL_VERSION,
    Act,
    Chat,
    Error,
    Hello,
    Leave,
    Message,
    Result,
    State,
    Welcome,
)


class ProtocolError(Exception):
    pass


def encode(message: Message) -> bytes:
    frame = _to_dict(message)
    return (json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes) -> Message:
    try:
        frame = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("bad frame") from exc
    if not isinstance(frame, dict) or "type" not in frame:
        raise ProtocolError("bad frame")
    kinds = {
        "hello": _hello, "welcome": _welcome, "act": _act, "chat": _chat,
        "leave": _leave, "state": _state, "result": _result, "error": _error,
    }
    builder = kinds.get(frame["type"])
    if builder is None:
        raise ProtocolError("unknown frame")
    return builder(frame)


def _to_dict(message: Message) -> dict:
    match message:
        case Hello():
            return {"type": "hello", "v": PROTOCOL_VERSION, "name": _text(message.name)}
        case Welcome():
            return {
                "type": "welcome", "seat": message.seat, "room": message.room,
                "names": message.names, "blinds": message.blinds, "stack": message.stack,
                "act_seconds": message.act_seconds,
            }
        case Act():
            return {"type": "act", "kind": _text(message.kind), "amount": _opt_int(message.amount)}
        case Chat():
            return {"type": "chat", "text": _text(message.text), "sender": _text(message.sender)}
        case Leave():
            return {"type": "leave"}
        case State():
            return {"type": "state", "view": _view_out(message.view)}
        case Result():
            return {"type": "result", "result": _result_out(message.result)}
        case Error():
            return {"type": "error", "code": _text(message.code)}
    raise ProtocolError("unknown message")


def _hello(frame: dict) -> Hello:
    version = _int(frame.get("v"))
    if version != PROTOCOL_VERSION:
        raise ProtocolError("version mismatch")
    return Hello(_text(frame.get("name")))


def _welcome(frame: dict) -> Welcome:
    return Welcome(
        seat=_int(frame.get("seat")),
        room=_text(frame.get("room")),
        names=[_text(n) for n in frame.get("names", [])],
        blinds=[_int(b) for b in frame.get("blinds", [])],
        stack=_int(frame.get("stack")),
        act_seconds=_float(frame.get("act_seconds")),
    )


def _act(frame: dict) -> Act:
    return Act(_text(frame.get("kind")), _opt_int(frame.get("amount")))


def _chat(frame: dict) -> Chat:
    return Chat(_text(frame.get("text")), _text(frame.get("sender")))


def _leave(frame: dict) -> Leave:
    return Leave()


def _state(frame: dict) -> State:
    view = frame.get("view")
    if not isinstance(view, dict):
        raise ProtocolError("bad view")
    return State(_view_in(view))


def _result(frame: dict) -> Result:
    data = frame.get("result")
    if not isinstance(data, dict):
        raise ProtocolError("bad result")
    return Result(_result_in(data))


def _error(frame: dict) -> Error:
    return Error(_text(frame.get("code")))


def _view_out(view: SeatView) -> dict:
    return {
        "hand_no": view.hand_no,
        "street": view.street.value,
        "button": view.button,
        "community": [str(c) for c in view.community],
        "pot_total": view.pot_total,
        "seats": [[s.index, s.name, s.stack, s.street_bet, s.folded, s.allin, s.is_button] for s in view.seats],
        "hole": [str(c) for c in view.hole] if view.hole is not None else None,
        "to_act": view.to_act,
        "legal": (
            [view.legal.can_check, view.legal.to_call, view.legal.min_raise_to, view.legal.max_raise_to]
            if view.legal is not None
            else None
        ),
        "log": list(view.log),
    }


def _view_in(data: dict) -> SeatView:
    try:
        return SeatView(
            hand_no=_int(data.get("hand_no")),
            street=Street(_text(data.get("street"))),
            button=_int(data.get("button")),
            community=tuple(_card(c) for c in data.get("community", [])),
            pot_total=_int(data.get("pot_total")),
            seats=tuple(
                SeatInfo(index=s[0], name=s[1], stack=s[2], street_bet=s[3], folded=s[4], allin=s[5], is_button=s[6])
                for s in data.get("seats", [])
            ),
            hole=tuple(_card(c) for c in data["hole"]) if data.get("hole") is not None else None,
            to_act=data.get("to_act"),
            legal=(
                LegalActions(leg[0], leg[1], leg[2], leg[3])
                if (leg := data.get("legal")) is not None
                else None
            ),
            deadline=None,
            log=tuple(data.get("log", [])),
        )
    except (TypeError, KeyError, ValueError) as exc:
        raise ProtocolError("bad view") from exc


def _result_out(result: HandResult) -> dict:
    return {
        "fold_win": result.fold_win,
        "awards": [[a.name, a.amount, _score_out(a.score)] for a in result.awards],
        "reveal": {name: [str(c) for c in cards] for name, cards in result.reveal.items()},
        "best": result.best,
        "pots": [list(p) for p in result.pots],
    }


def _result_in(data: dict) -> HandResult:
    try:
        return HandResult(
            fold_win=bool(data.get("fold_win")),
            awards=tuple(
                Award(name=a[0], amount=a[1], score=_score_in(a[2]))
                for a in data.get("awards", [])
            ),
            reveal={name: tuple(_card(c) for c in cards) for name, cards in data.get("reveal", {}).items()},
            best=dict(data.get("best", {})),
            pots=tuple((p[0], tuple(p[1])) for p in data.get("pots", [])),
        )
    except (TypeError, KeyError, IndexError) as exc:
        raise ProtocolError("bad result") from exc


def _score_out(score: HandScore | None) -> list | None:
    if score is None:
        return None
    return [score.kind.value, list(score.tiebreak)]


def _score_in(data: list | None) -> HandScore | None:
    if data is None:
        return None
    return HandScore(HandKind(data[0]), tuple(data[1]))


def _card(text: str) -> Card:
    rank_text, suit_text = text[:-1], text[-1]
    face = {"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
    rank = face.get(rank_text) if rank_text.isalpha() else int(rank_text) if rank_text.isdigit() else None
    if rank is None or suit_text not in Suit:
        raise ProtocolError("bad card")
    return Card(rank, Suit(suit_text))


def _text(value) -> str:
    if not isinstance(value, str):
        raise ProtocolError("expected string")
    return value


def _int(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolError("expected int")
    return value


def _float(value) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProtocolError("expected number")
    return float(value)


def _opt_int(value) -> int | None:
    return None if value is None else _int(value)
