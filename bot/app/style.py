"""Пост-обработка ответа. Промпт задаёт стиль, этот файл его удерживает.

Модель почти всегда сползает к вежливому ассистенту на длинных диалогах
и к простыням — на коротких вопросах. Дешевле вычистить сползание здесь,
чем каждый раз просить не сползать.
"""
from __future__ import annotations

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_MD_LIST = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)


def _normalize_breaks(text: str) -> str:
    """Модель ставит переносы посреди фразы — склеиваем обратно.

    Абзацем считается только двойной перенос. Без этого обрезка рубит
    предложение пополам, а в чате получается лесенка.
    """
    text = re.sub(r"\n{2,}", "\x00", text)
    text = text.replace("\n", " ").replace("\x00", "\n\n")
    return re.sub(r"[ \t]{2,}", " ", text)


def _strip_openers(text: str, openers: list[str]) -> str:
    """Срезает «Конечно,» / «Понимаю,» в начале."""
    for op in openers:
        text = re.sub(rf"^\s*{re.escape(op)}[\s,!.—-]+", "", text, count=1, flags=re.IGNORECASE)
    return text


def _drop_banned_sentences(text: str, phrases: list[str]) -> str:
    """Выбрасывает предложения с запрещённым оборотом, сохраняя абзацы."""
    if not phrases:
        return text
    out: list[str] = []
    for para in text.split("\n\n"):
        keep = [s for s in _SENT_SPLIT.split(para) if not any(p in s.lower() for p in phrases)]
        if keep:
            out.append(" ".join(keep))
    return "\n\n".join(out)


def _condense(text: str, max_sentences: int, max_chars: int) -> str:
    """Ужимает ответ, сохраняя первый абзац и последнюю фразу.

    Последняя фраза — это действие, ради которого весь ответ, а первый
    абзац — гул. Поэтому лишнее выкидывается из середины, а не с хвоста.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text

    head, body = paragraphs[0], paragraphs[1:]
    sentences = [s.strip() for para in body for s in _SENT_SPLIT.split(para) if s.strip()]
    if not sentences:
        return head

    def over() -> bool:
        too_many = max_sentences > 0 and 1 + len(sentences) > max_sentences
        too_long = max_chars > 0 and len(head) + sum(len(s) + 1 for s in sentences) > max_chars
        return too_many or too_long

    while len(sentences) > 2 and over():
        sentences.pop(1)
    if len(sentences) > 1 and over():
        sentences = sentences[-1:]

    return head + "\n\n" + " ".join(sentences)


def enforce(
    text: str,
    *,
    banned_phrases: list[str],
    banned_openers: list[str],
    max_sentences: int = 4,
    max_chars: int = 0,
    allow_lists: bool = False,
) -> str:
    text = text.strip()
    # Модель любит оборачивать ответ в кавычки или ```-блок.
    text = re.sub(r"^```[a-z]*\n?|```$", "", text).strip()
    text = _normalize_breaks(text)
    text = _strip_openers(text, banned_openers)
    text = _drop_banned_sentences(text, [p.lower() for p in banned_phrases])

    if not allow_lists and _MD_LIST.search(text):
        text = _MD_LIST.sub("", text)

    text = _condense(text, max_sentences, max_chars)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
