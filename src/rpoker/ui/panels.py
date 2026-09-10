from __future__ import annotations

from dataclasses import dataclass

from rpoker.domain.actions import Action, LegalActions


@dataclass(frozen=True, slots=True)
class ActionItem:
    kind: str
    label: str
    hotkey: str


def action_items(legal: LegalActions) -> tuple[ActionItem, ...]:
    items = []
    if legal.to_call > 0:
        items.append(ActionItem("fold", "弃牌", "F"))
        items.append(ActionItem("call", f"跟注 {legal.to_call}", "C"))
    else:
        items.append(ActionItem("check", "过牌", "C"))
    if legal.max_raise_to is not None:
        items.append(ActionItem("raise", "加注", "R"))
        if legal.to_call > 0:
            items.append(ActionItem("allin", "全下", "A"))
    return tuple(items)


def auto_action(legal: LegalActions) -> Action:
    return Action("check") if legal.can_check else Action("fold")


def parse_action(answer: str, legal: LegalActions) -> Action | None:
    if answer == "f":
        return Action("fold")
    if answer == "c":
        return Action("check") if legal.can_check else Action("call")
    if answer == "a" and legal.to_call > 0:
        return Action("allin")
    if answer.startswith("r") and legal.max_raise_to is not None and answer[1:].isdigit():
        amount = int(answer[1:])
        if legal.min_raise_to <= amount <= legal.max_raise_to:
            return Action("raise", amount)
    return None


def action_line(legal: LegalActions) -> str:
    parts = []
    if legal.to_call > 0:
        parts.append("f=弃牌")
        parts.append(f"c=跟注 {legal.to_call}")
        parts.append("a=全下")
    else:
        parts.append("c=过牌")
    if legal.max_raise_to is not None:
        parts.append(f"r=加注 {legal.min_raise_to}-{legal.max_raise_to}")
    return "  ".join(parts) + "  （如 r120 表示加注至 120）"


@dataclass(slots=True)
class ActionPanel:
    """Interaction state machine for one turn; rendering reads, only keys mutate."""

    legal: LegalActions
    selected: int = 0
    raising: bool = False
    amount: int = 0

    @classmethod
    def build(cls, legal: LegalActions) -> ActionPanel:
        return cls(legal)

    def items(self) -> tuple[ActionItem, ...]:
        return action_items(self.legal)

    def handle(self, key: str, pot_total: int) -> Action | None:
        """Consume one action-scope key. Returns an Action to submit, None to keep waiting."""
        if self.raising:
            return self._handle_raise(key, pot_total)
        items = self.items()
        match key:
            case "up":
                self.selected = (self.selected - 1) % len(items)
            case "down":
                self.selected = (self.selected + 1) % len(items)
            case "enter":
                return self._commit(items[self.selected].kind, pot_total)
            case "f":
                return Action("fold")
            case "c" | "a" | "r" as hotkey if item := _by_hotkey(items, hotkey):
                return self._commit(item.kind, pot_total)
            case digit if digit.isdigit() and 1 <= int(digit) <= len(items):
                return self._commit(items[int(digit) - 1].kind, pot_total)
        return None

    def _commit(self, kind: str, pot_total: int) -> Action | None:
        match kind:
            case "raise":
                self.raising = True
                self.amount = self.legal.min_raise_to
                return None
            case "check":
                return Action("check")
            case "call":
                return Action("call")
            case "allin":
                return Action("allin")
            case _:
                return Action("fold")

    def _handle_raise(self, key: str, pot_total: int) -> Action | None:
        low, high = self.legal.min_raise_to, self.legal.max_raise_to
        step = max(pot_total // 20, 1)
        presets = {
            "1": low,
            "2": min(max(self.legal.to_call + pot_total // 2, low), high),
            "3": min(max(self.legal.to_call + pot_total, low), high),
            "4": high,
        }
        match key:
            case "left":
                self.amount = max(low, self.amount - step)
            case "right":
                self.amount = min(high, self.amount + step)
            case "shift-left":
                self.amount = max(low, self.amount - step * 10)
            case "shift-right":
                self.amount = min(high, self.amount + step * 10)
            case "enter":
                return Action("raise", self.amount)
            case "escape" | "q":
                self.raising = False
            case digit if digit in presets:
                self.amount = presets[digit]
        return None


def _by_hotkey(items: tuple[ActionItem, ...], hotkey: str) -> ActionItem | None:
    return next((item for item in items if item.hotkey == hotkey.upper()), None)
