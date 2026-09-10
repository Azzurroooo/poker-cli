from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass(slots=True)
class Settings:
    nickname: str = ""
    theme: str = "onedark"
    display: str = "rich"
    blinds: tuple[int, int] = (5, 10)
    starting_stack: int = 1000
    table_size: int = 5
    act_seconds: float = 30.0

    @staticmethod
    def path() -> Path:
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        return Path(base) / "poker-cli" / "config.json"

    @classmethod
    def load(cls) -> Settings:
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        blinds = clean.pop("blinds", None)
        settings = cls(**clean)
        if isinstance(blinds, list) and len(blinds) == 2:
            settings.blinds = (blinds[0], blinds[1])
        return settings

    def save(self) -> None:
        data = asdict(self)
        data["blinds"] = list(self.blinds)
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
