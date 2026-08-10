"""Команды и диалог. Логика тонкая — вся тяжесть в персоне и памяти."""
from __future__ import annotations

import logging
import re
import time
from time import monotonic
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import Message as TgMessage

from . import persona as personas
from . import safety, style
from .config import settings
from .llm import LLMError, llm
from .memory import memory

log = logging.getLogger(__name__)
router = Router()

_last_seen: dict[int, float] = {}

GENESIS = (
    "Ветка заведена. Первая запись пустая.\n\n"
    "Я не помогаю и не поддерживаю — я снимаю показания и говорю, что вижу. "
    "Всё, что ты сейчас про себя думаешь, — конфигурация, а не приговор.\n\n"
    "<code>/pulse</code> — краш-тест дня\n"
    "<code>/fork</code> — развилка\n"
    "<code>/seal</code> — запечатать ветку\n"
    "<code>/audit</code> — недельный аудит\n"
    "<code>/voice</code> — сменить голос\n\n"
    "Или просто напиши, что происходит."
)

DOSSIER_PROMPT = (
    "Ниже фрагмент разговора. Собери сжатое досье на человека для внутренней "
    "памяти: повторяющиеся темы, режим дня, что его держит, что рассыпается, "
    "как он говорит о себе. До 120 слов, тезисами, без оценок и без обращения "
    "к нему. Только факты и повторы."
)


_ALLOWED_TAGS = (
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "tg-spoiler", "blockquote",
)
_TAG_BACK = re.compile(r"&lt;(/?)(" + "|".join(_ALLOWED_TAGS) + r")&gt;", re.IGNORECASE)
_TAG_ANY = re.compile(r"<(/?)([a-z-]+)>")


def _balanced(html: str) -> bool:
    """Телеграм падает на незакрытом теге — проверяем до отправки."""
    stack: list[str] = []
    for closing, tag in _TAG_ANY.findall(html):
        if closing:
            if not stack or stack.pop() != tag:
                return False
        else:
            stack.append(tag)
    return not stack


def _to_telegram(text: str) -> str:
    """Экранируем всё, потом возвращаем только разрешённые теги.

    Так модель сама решает, что выделить, а случайные < и & не ломают
    разбор. Если разметка кривая — отдаём чистый текст, это не страшно.
    """
    out = _TAG_BACK.sub(lambda m: f"<{m.group(1)}{m.group(2).lower()}>", escape(text))
    return out if _balanced(out) else escape(_TAG_ANY.sub("", text))


def _throttled(user_id: int) -> bool:
    now = time.monotonic()
    if now - _last_seen.get(user_id, 0.0) < settings.rate_limit_seconds:
        return True
    _last_seen[user_id] = now
    return False


async def _respond(msg: TgMessage, user_text: str, *, directive: str | None = None) -> None:
    """Один проход: собрать контекст → сгенерировать → вычистить → ответить."""
    user_id = msg.from_user.id
    row = await memory.ensure_user(msg.from_user, msg.chat.id)
    p = personas.load(row["persona"])

    # Красная линия отменяет персону целиком.
    if safety.is_red_line(user_text):
        await msg.bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
        reply = await llm.complete(
            safety.PLAIN_SYSTEM,
            [*(await memory.history(user_id, 4)), {"role": "user", "content": user_text}],
            temperature=0.4,
        )
        await memory.add(user_id, "user", user_text,
                         chat_id=msg.chat.id, tg_msg_id=msg.message_id)
        await memory.add(user_id, "assistant", reply, chat_id=msg.chat.id)
        await msg.answer(reply)
        return

    system = p.build_system(personas.LAWS, row["dossier"])
    if directive:
        system += f"\n\n---\n\n## Режим этого ответа\n{directive.strip()}"

    history = await memory.history(user_id)
    messages = [*p.few_shot(), *history, {"role": "user", "content": user_text}]

    await msg.bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
    started = monotonic()
    try:
        raw = await llm.complete(system, messages, temperature=p.temperature)
    except LLMError as exc:
        log.exception("LLM недоступен")
        await memory.log(user_id, "error", str(exc)[:400])
        await msg.answer("Прибор не отвечает. Попробуй через минуту.")
        return
    latency = int((monotonic() - started) * 1000)

    reply = style.enforce(
        raw,
        banned_phrases=p.banned_phrases,
        banned_openers=p.banned_openers,
        max_sentences=p.max_sentences if directive is None else p.max_sentences + 2,
        max_chars=p.max_chars if directive is None else int(p.max_chars * 1.6),
    )
    if not reply:
        reply = raw.strip()[:1000] or "Показания не сняты. Переформулируй."

    turns = await memory.add(user_id, "user", user_text, persona=p.id,
                         chat_id=msg.chat.id, tg_msg_id=msg.message_id)
    await memory.add(
        user_id, "assistant", reply, raw=raw, chat_id=msg.chat.id,
        persona=p.id, model=settings.llm_model, latency_ms=latency,
    )
    try:
        await msg.answer(_to_telegram(reply), parse_mode="HTML")
    except TelegramBadRequest:
        log.warning("Телеграм не принял разметку, шлю без неё")
        await msg.answer(_TAG_ANY.sub("", reply))

    if turns and turns % settings.dossier_every == 0:
        await _rebuild_dossier(user_id)


async def _rebuild_dossier(user_id: int) -> None:
    history = await memory.history(user_id, limit=settings.dossier_every * 2)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    try:
        dossier = await llm.complete(
            DOSSIER_PROMPT, [{"role": "user", "content": transcript}], temperature=0.3
        )
        await memory.set_dossier(user_id, dossier)
    except LLMError:
        log.warning("Досье не пересобрано для %s", user_id)


# --- команды ----------------------------------------------------------

@router.message(CommandStart())
async def start(msg: TgMessage) -> None:
    await memory.ensure_user(msg.from_user, msg.chat.id)
    await memory.log(msg.from_user.id, "start")
    await msg.answer(GENESIS, parse_mode="HTML")


@router.message(Command("pulse", "fork", "seal", "audit"))
async def ritual(msg: TgMessage) -> None:
    if _throttled(msg.from_user.id):
        return
    command = msg.text.split()[0].lstrip("/").split("@")[0]
    payload = msg.text.partition(" ")[2].strip()

    row = await memory.ensure_user(msg.from_user, msg.chat.id)
    p = personas.load(row["persona"])
    directive = p.commands.get(command, "")

    if command == "audit":
        entries = await memory.ledger(msg.from_user.id)
        payload = "\n".join(f"{e['ts']} · {e['kind']} · {e['payload'][:120]}" for e in entries)
        payload = payload or "Журнал пуст."

    await memory.log(msg.from_user.id, command, payload or "—")
    await _respond(msg, payload or f"[{command}]", directive=directive)


@router.message(Command("voice"))
async def voice(msg: TgMessage) -> None:
    arg = msg.text.partition(" ")[2].strip()
    catalogue = personas.available()
    ids = {p.id for p in catalogue}

    if arg in ids:
        await memory.set_persona(msg.from_user.id, arg)
        await memory.log(msg.from_user.id, "voice", arg)
        await msg.answer(f"Голос переключён: {arg}")
        return

    listing = "\n".join(f"<code>/voice {p.id}</code> — {p.name}, {p.tagline}" for p in catalogue)
    await msg.answer("Доступные голоса:\n\n" + listing, parse_mode="HTML")


@router.message(Command("wipe"))
async def wipe(msg: TgMessage) -> None:
    await memory.log(msg.from_user.id, "wipe")
    await memory.wipe(msg.from_user.id)
    await msg.answer("Стёрто. История, досье, журнал. Ветка закрыта без следа.")


@router.message(F.text & ~F.text.startswith("/"))
async def chat(msg: TgMessage) -> None:
    if _throttled(msg.from_user.id):
        return
    await _respond(msg, msg.text)
