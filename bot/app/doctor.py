"""Проверка окружения. Запускать до бота:  python -m app.doctor

Отвечает на вопрос «почему не работает» до того, как ты его задашь.
"""
from __future__ import annotations

import asyncio
import sys

OK = "  \033[32m✓\033[0m"
BAD = "  \033[31m✗\033[0m"
WARN = "  \033[33m!\033[0m"


async def check() -> int:
    problems = 0
    print("\n\033[1mПРОВЕРКА ОКРУЖЕНИЯ\033[0m")
    print("─" * 46)

    # 1. Конфигурация
    try:
        from .config import settings
    except SystemExit as exc:
        print(f"{BAD} Конфигурация не читается")
        print(f"     {exc}")
        return 1
    print(f"{OK} .env прочитан")

    # 2. Телеграм
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.get(
                f"https://api.telegram.org/bot{settings.bot_token}/getMe"
            )
            data = r.json()
            if data.get("ok"):
                username = data["result"]["username"]
                print(f"{OK} Телеграм отвечает — бот @{username}")
            else:
                print(f"{BAD} Телеграм отклонил токен: {data.get('description')}")
                print("     Проверь BOT_TOKEN в .env — обычно теряется символ при копировании")
                problems += 1
        except httpx.HTTPError as exc:
            print(f"{BAD} Телеграм недоступен: {exc}")
            problems += 1

    # 3. Персоны
    from . import persona as personas

    try:
        catalogue = personas.available()
        names = ", ".join(p.id for p in catalogue)
        print(f"{OK} Персоны загружены: {names}")
        if settings.persona not in {p.id for p in catalogue}:
            print(f"{BAD} PERSONA={settings.persona} — такого файла нет в bot/personas")
            problems += 1
    except Exception as exc:  # noqa: BLE001 — тут важно показать любую поломку YAML
        print(f"{BAD} Персона не читается: {exc}")
        print("     Скорее всего сбит отступ в YAML. Отступы — только пробелы, не табы.")
        problems += 1

    if not personas.LAWS.strip():
        print(f"{WARN} docs/LAWS.md пустой или не найден — бот будет без законов")

    # 4. Нейросеть
    from .llm import LLMError, llm

    if not settings.llm_api_key:
        print(f"{BAD} LLM_API_KEY пустой")
        problems += 1
    else:
        try:
            reply = await llm.complete(
                "Отвечай одним словом.",
                [{"role": "user", "content": "скажи: работает"}],
                temperature=0,
                retries=0,
            )
            print(f"{OK} Нейросеть отвечает ({settings.llm_model}): {reply[:40]}")
        except LLMError as exc:
            print(f"{BAD} Нейросеть не отвечает: {str(exc)[:180]}")
            if "credit" in str(exc).lower() or "balance" in str(exc).lower():
                print("     Пополни баланс в консоли провайдера.")
            elif "401" in str(exc) or "authentication" in str(exc).lower():
                print("     Ключ неверный. Проверь LLM_API_KEY.")
            elif "model" in str(exc).lower():
                print(f"     Модель '{settings.llm_model}' недоступна. Проверь LLM_MODEL.")
            problems += 1
        finally:
            await llm.close()

    # 5. Память
    from .memory import memory

    try:
        await memory.open()
        await memory.close()
        print(f"{OK} База пишется: {memory.backend}")
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} База не пишется: {exc}")
        problems += 1

    print("─" * 46)
    if problems:
        print(f"\033[31mПроблем: {problems}. Чини сверху вниз.\033[0m\n")
    else:
        print("\033[32mВсё на месте. Запускай: python -m app.main\033[0m\n")
    return problems


def main() -> None:
    sys.exit(1 if asyncio.run(check()) else 0)


if __name__ == "__main__":
    main()
