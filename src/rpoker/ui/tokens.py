from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Theme:
    fg: str
    dim: str
    accent: str
    good: str
    bad: str
    gold: str
    border: str
    club: str
    diamond: str
    heart: str
    spade: str


THEMES: dict[str, Theme] = {
    "onedark": Theme(
        fg="#abb2bf", dim="#5c6370", accent="#61afef", good="#98c379", bad="#e06c75",
        gold="#e5c07b", border="#3e4451", club="#98c379", diamond="#61afef",
        heart="#e06c75", spade="#8da3c7",
    ),
    "rosepine": Theme(
        fg="#e0def4", dim="#908caa", accent="#c4a7e7", good="#9ccfd8", bad="#eb6f92",
        gold="#f6c177", border="#403d52", club="#9ccfd8", diamond="#c4a7e7",
        heart="#eb6f92", spade="#908caa",
    ),
    "ansi16": Theme(
        fg="white", dim="bright_black", accent="bright_blue", good="green", bad="red",
        gold="yellow", border="bright_black", club="green", diamond="bright_blue",
        heart="red", spade="bright_cyan",
    ),
}


def suit_color(suit: str, theme: Theme) -> str:
    return {"♣": theme.club, "♦": theme.diamond, "♥": theme.heart, "♠": theme.spade}[suit]
