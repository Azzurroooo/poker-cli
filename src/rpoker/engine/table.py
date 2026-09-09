from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from rpoker.domain.actions import Action, LegalActions
from rpoker.domain.cards import Card, Deck, HandScore, best_five
from rpoker.domain.views import SeatInfo, SeatView, Street
from rpoker.engine.pots import build_pots, uncalled_refund


class PokerError(Exception):
    pass


@dataclass(slots=True)
class _Seat:
    name: str
    stack: int
    street_bet: int = 0
    committed: int = 0
    folded: bool = False
    allin: bool = False
    has_acted: bool = False
    hole: tuple[Card, ...] = ()


@dataclass(frozen=True, slots=True)
class Award:
    name: str
    amount: int
    score: HandScore | None


@dataclass(frozen=True, slots=True)
class HandResult:
    fold_win: bool
    awards: tuple[Award, ...]
    reveal: dict[str, tuple[Card, ...]]
    best: dict[str, str]
    pots: tuple[tuple[int, tuple[str, ...]], ...]


_NEXT_STREET = {
    Street.PREFLOP: Street.FLOP,
    Street.FLOP: Street.TURN,
    Street.TURN: Street.RIVER,
}
_CARDS_PER_STREET = {Street.FLOP: 3, Street.TURN: 1, Street.RIVER: 1}


class Table:
    def __init__(
        self,
        names: Sequence[str],
        stacks: Sequence[int],
        blinds: tuple[int, int],
        rng: random.Random,
        now: Callable[[], float] = time.monotonic,
        act_seconds: float = 30.0,
        deck_order: Sequence[Card] | None = None,
    ) -> None:
        self._seats = [_Seat(n, s) for n, s in zip(names, stacks)]
        self.blinds = blinds
        self._rng = rng
        self._now = now
        self.act_seconds = act_seconds
        self._deck_order = deck_order
        self.hand_no = 0
        self.street = Street.WAITING
        self.button = len(names) - 1
        self.community: tuple[Card, ...] = ()
        self.pot = 0
        self._deck: Deck | None = None
        self._current_bet = 0
        self._last_raise = blinds[1]
        self.to_act: int | None = None
        self._deadline: float | None = None
        self.log: tuple[str, ...] = ()
        self.hand_result: HandResult | None = None

    @property
    def finished(self) -> bool:
        return sum(1 for s in self._seats if s.stack > 0) <= 1

    def start_hand(self) -> None:
        if self.finished:
            raise PokerError("table is finished")
        self.hand_no += 1
        self.button = self._next_alive(self.button)
        for s in self._seats:
            s.street_bet = s.committed = 0
            s.folded = s.allin = s.has_acted = False
            s.hole = ()
            if s.stack == 0:
                s.folded = True
        self.community = ()
        self.pot = 0
        self._current_bet = 0
        self._last_raise = self.blinds[1]
        self.log = (f"—— 第 {self.hand_no} 手 ——",)
        self.hand_result = None
        self.street = Street.PREFLOP
        self._deck = Deck(self._rng, order=self._deck_order)
        n = len(self._seats)
        sb = self.button if n == 2 else self._next_alive(self.button)
        bb = self._next_alive(sb)
        self._post_blind(sb, self.blinds[0])
        self._post_blind(bb, self.blinds[1])
        for _ in range(2):
            for step in range(n):
                seat = (self.button + 1 + step) % n
                if self._seats[seat].stack > 0:
                    self._seats[seat].hole += self._deck.deal(1)
        self._set_to_act(sb if n == 2 else self._next_pending(bb))
        self.log = (
            *self.log,
            f"{self._seats[sb].name} 小盲 {self._seats[sb].street_bet} · {self._seats[bb].name} 大盲 {self._seats[bb].street_bet}",
        )

    def apply(self, seat: int, action: Action) -> None:
        if seat != self.to_act or self.street is Street.HAND_OVER:
            raise PokerError(f"not {self._seats[seat].name}'s turn")
        s = self._seats[seat]
        match action.kind:
            case "fold":
                s.folded = True
                self.log = (*self.log, f"{s.name} 弃牌")
            case "check":
                if self._legal(seat).to_call > 0:
                    raise PokerError("cannot check facing a bet")
                self.log = (*self.log, f"{s.name} 过牌")
            case "call":
                pay = min(self._legal(seat).to_call, s.stack)
                self._pay(s, pay)
                self.log = (*self.log, f"{s.name} 跟注 {pay}" + ("（全下）" if s.allin else ""))
            case "raise":
                target = action.amount
                if target is None or self._is_illegal_raise(target, self._legal(seat)):
                    raise PokerError("illegal raise")
                self._raise(s, target)
            case "allin":
                total = s.stack + s.street_bet
                legal = self._legal(seat)
                if legal.max_raise_to is None or total <= self._current_bet:
                    pay = min(legal.to_call, s.stack)
                    self._pay(s, pay)
                    self.log = (*self.log, f"{s.name} 全下跟注 {pay}")
                else:
                    self._raise(s, total)
            case _:
                raise PokerError(f"unknown action {action.kind}")
        if action.kind != "fold":
            s.has_acted = True
        active = [i for i, s in enumerate(self._seats) if not s.folded]
        if len(active) == 1:
            self._fold_win(active[0])
        else:
            self._set_to_act(self._next_pending(seat))

    def advance_street(self) -> None:
        if self.to_act is not None or self.street is Street.HAND_OVER:
            raise PokerError("street not complete")
        self._collect()
        if self.street is Street.RIVER:
            self._showdown()
            return
        street = _NEXT_STREET[self.street]
        self.street = street
        dealt = self._deck.deal(_CARDS_PER_STREET[street])
        self.community += dealt
        self._current_bet = 0
        self._last_raise = self.blinds[1]
        for s in self._seats:
            s.has_acted = False
        self.log = (*self.log, f"—— {street.value} {' '.join(map(str, dealt))}")
        self._set_to_act(self._next_pending(self.button))

    def seat_view(self, seat: int | None) -> SeatView:
        infos = tuple(
            SeatInfo(i, s.name, s.stack, s.street_bet, s.folded, s.allin, i == self.button)
            for i, s in enumerate(self._seats)
        )
        mine = seat is not None and seat == self.to_act
        return SeatView(
            hand_no=self.hand_no,
            street=self.street,
            button=self.button,
            community=self.community,
            pot_total=self.pot + sum(s.street_bet for s in self._seats),
            seats=infos,
            hole=self._seats[seat].hole if seat is not None else None,
            to_act=self.to_act,
            legal=self._legal(self.to_act) if mine else None,
            deadline=self._deadline if mine else None,
            log=self.log,
        )

    def _next_alive(self, seat: int) -> int:
        n = len(self._seats)
        for step in range(1, n + 1):
            i = (seat + step) % n
            if self._seats[i].stack > 0:
                return i
        raise PokerError("no alive seat")

    def _next_pending(self, after: int) -> int | None:
        n = len(self._seats)
        can_bet = sum(1 for s in self._seats if not s.folded and not s.allin and s.stack > 0) >= 2
        for step in range(1, n + 1):
            i = (after + step) % n
            s = self._seats[i]
            if s.stack == 0 or s.folded or s.allin:
                continue
            if s.street_bet < self._current_bet:
                return i
            if not s.has_acted and can_bet:
                return i
        return None

    def _post_blind(self, seat: int, amount: int) -> None:
        s = self._seats[seat]
        self._pay(s, min(amount, s.stack))
        self._current_bet = max(self._current_bet, s.street_bet)

    def _pay(self, s: _Seat, amount: int) -> None:
        s.stack -= amount
        s.street_bet += amount
        s.committed += amount
        if s.stack == 0:
            s.allin = True

    def _raise(self, s: _Seat, target: int) -> None:
        was_bet = self._current_bet == 0
        self._pay(s, target - s.street_bet)
        if target > self._current_bet:
            if target - self._current_bet >= self._last_raise:
                for other in self._seats:
                    if other is not s and not other.folded and not other.allin:
                        other.has_acted = False
                self._last_raise = target - self._current_bet
            self._current_bet = target
        verb = "全下" if s.allin else ("下注" if was_bet else "加注至")
        self.log = (*self.log, f"{s.name} {verb} {target}")

    def _is_illegal_raise(self, target: int, legal: LegalActions) -> bool:
        if legal.max_raise_to is None:
            return True
        return target > legal.max_raise_to or (target < legal.min_raise_to and target != legal.max_raise_to)

    def _legal(self, seat: int | None) -> LegalActions:
        if seat is None:
            return LegalActions(False, 0, None, None)
        s = self._seats[seat]
        to_call = max(self._current_bet - s.street_bet, 0)
        total = s.stack + s.street_bet
        if s.has_acted or s.stack <= to_call:
            return LegalActions(to_call == 0, to_call, None, None)
        base = self.blinds[1] if self._current_bet == 0 else self._current_bet + self._last_raise
        return LegalActions(to_call == 0, to_call, min(base, total), total)

    def _set_to_act(self, seat: int | None) -> None:
        self.to_act = seat
        self._deadline = self._now() + self.act_seconds if seat is not None else None

    def _collect(self) -> None:
        self.pot += sum(s.street_bet for s in self._seats)
        for s in self._seats:
            s.street_bet = 0

    def _fold_win(self, winner: int) -> None:
        self._collect()
        committed = {i: s.committed for i, s in enumerate(self._seats) if s.committed}
        refund, seat = uncalled_refund(committed)
        if refund:
            self._seats[seat].stack += refund
        name = self._seats[winner].name
        amount = self.pot - refund
        self._seats[winner].stack += amount
        self.log = (*self.log, f"其余玩家全部弃牌，{name} 不亮牌收下 {amount}")
        self.hand_result = HandResult(
            fold_win=True,
            awards=(Award(name, amount, None),),
            reveal={},
            best={},
            pots=((amount, (name,)),),
        )
        self.street = Street.HAND_OVER
        self._set_to_act(None)

    def _showdown(self) -> None:
        committed = {i: s.committed for i, s in enumerate(self._seats) if s.committed}
        refund, seat = uncalled_refund(committed)
        if refund:
            self._seats[seat].stack += refund
            committed[seat] -= refund
            self.log = (*self.log, f"未被跟注的 {refund} 退还 {self._seats[seat].name}")
        live = [i for i, s in enumerate(self._seats) if not s.folded]
        scores = {i: best_five((*self._seats[i].hole, *self.community)) for i in live}
        folded = {i for i, s in enumerate(self._seats) if s.folded}
        pots = build_pots(committed, folded)
        won = {i: 0 for i in live}
        pot_lines = []
        for pot in pots:
            contenders = [i for i in live if i in pot.eligible]
            top = max(scores[i][0] for i in contenders)
            winners = [i for i in contenders if scores[i][0] == top]
            share, remainder = divmod(pot.amount, len(winners))
            order = sorted(winners, key=lambda i: (i - self.button - 1) % len(self._seats))
            for offset, i in enumerate(order):
                won[i] += share + (1 if offset < remainder else 0)
            pot_lines.append((pot.amount, tuple(self._seats[i].name for i in order)))
        awards = []
        for i in sorted(won, key=lambda i: (-won[i], i)):
            if won[i] > 0:
                self._seats[i].stack += won[i]
                awards.append(Award(self._seats[i].name, won[i], scores[i][0]))
                self.log = (*self.log, f"{self._seats[i].name} 以 {scores[i][0].label()} 赢得 {won[i]}")
        self.hand_result = HandResult(
            fold_win=False,
            awards=tuple(awards),
            reveal={self._seats[i].name: self._seats[i].hole for i in live},
            best={self._seats[i].name: " ".join(map(str, scores[i][1])) for i in live},
            pots=tuple(pot_lines),
        )
        self.street = Street.HAND_OVER
        self._set_to_act(None)
