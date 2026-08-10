"""Персона = YAML + законы. Характер не живёт в Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import settings


@dataclass(slots=True)
class Persona:
    id: str
    name: str
    tagline: str
    system: str
    temperature: float = 0.9
    max_sentences: int = 4
    max_chars: int = 0
    examples: list[dict] = field(default_factory=list)
    banned_phrases: list[str] = field(default_factory=list)
    banned_openers: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)

    def build_system(self, laws: str, dossier: str | None = None) -> str:
        """Системный промпт = характер + законы + досье на человека."""
        parts = [self.system.strip(), "## Законы, которые нельзя нарушать\n" + laws.strip()]

        if self.examples:
            demo = "\n\n".join(
                f"Человек пишет: {str(ex['user']).strip()}\n"
                f"Ты отвечаешь:\n{str(ex['assistant']).strip()}"
                for ex in self.examples
            )
            parts.append(
                "## Образцы твоего голоса\n"
                "ЭТО УЧЕБНЫЕ ОБРАЗЦЫ, А НЕ ИСТОРИЯ ВАШЕГО РАЗГОВОРА.\n"
                "Человек, с которым ты говоришь, НИЧЕГО из этого тебе не писал. "
                "Не ссылайся на их содержание, не считай, что он говорил о работе, "
                "расставании или пустоте, и не спорь с ним об этом. "
                "Бери отсюда только манеру речи и длину ответа.\n\n" + demo
            )

        if dossier:
            parts.append(
                "## Что ты уже знаешь об этом человеке\n"
                f"{dossier.strip()}\n"
                "Не пересказывай это вслух. Просто помни."
            )
        return "\n\n---\n\n".join(parts)

    def few_shot(self) -> list[dict[str, str]]:
        """Пусто намеренно: образцы живут в системном промпте."""
        return []


def _read_laws() -> str:
    path: Path = settings.laws_path
    return path.read_text(encoding="utf-8") if path.exists() else ""


LAWS = _read_laws()


def load(persona_id: str | None = None) -> Persona:
    pid = persona_id or settings.persona
    path = settings.personas_dir / f"{pid}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Нет персоны: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Persona(**data)


def available() -> list[Persona]:
    return [load(p.stem) for p in sorted(settings.personas_dir.glob("*.yaml"))]
