"""Запись всего входящего потока.

Это внешняя прослойка: она срабатывает ДО обработчиков и независимо от
того, взялся ли за сообщение хоть один из них. Поэтому в журнал попадает
всё — команды, обычный текст, стикеры, голосовые, фото, и даже то, что
бот проигнорировал.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from .memory import memory

log = logging.getLogger(__name__)


def _kind(msg: Message) -> str:
    text = msg.text or ""
    if text.startswith("/"):
        return "cmd:" + text[1:].split()[0].split("@")[0]
    return str(msg.content_type or "unknown")


def _payload(msg: Message) -> str | None:
    body = msg.text or msg.caption
    return body[:2000] if body else None


class TrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        msg = event if isinstance(event, Message) else None
        if msg is not None and msg.from_user is not None:
            try:
                await memory.ensure_user(msg.from_user, msg.chat.id)
                await memory.log(
                    msg.from_user.id,
                    _kind(msg),
                    _payload(msg),
                    chat_id=msg.chat.id,
                    username=msg.from_user.username,
                    message_id=msg.message_id,
                )
            except Exception:  # noqa: BLE001 — журнал не должен ронять бота
                log.exception("Событие не записано")
        return await handler(event, data)
