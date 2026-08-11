"""Справка о состоянии обратимости — картинка, а не нейросеть.

Рисуется кодом из показаний журнала. Стоит ноль, выглядит как документ,
которым хочется поделиться.
"""
from __future__ import annotations

import io
import math
import random
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1000, 1414                     # пропорции листа A4

PAPER = (201, 196, 180)
PAPER_DARK = (186, 181, 165)
INK = (31, 36, 32)
FADE = (96, 102, 92)
SEAL = (142, 58, 52)

# Кириллица есть далеко не везде: перебираем, что найдётся.
SANS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
SANS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _paper() -> Image.Image:
    """Фактура бумаги. Наносится ДО печати, иначе шум съедает буквы."""
    base = Image.new("RGB", (W, H), PAPER)

    grain = Image.effect_noise((W // 3, H // 3), 24).resize((W, H))
    grain = grain.filter(ImageFilter.GaussianBlur(0.9))
    grain = grain.point(lambda v: int(128 + (v - 128) * 0.30))
    base = ImageChops.soft_light(base, Image.merge("RGB", (grain, grain, grain)))

    # редкие пятна и заломы — лист лежал не в архиве
    marks = Image.new("RGB", (W, H), (255, 255, 255))
    md = ImageDraw.Draw(marks)
    rnd = random.Random(7)
    for _ in range(90):
        x, y = rnd.randrange(W), rnd.randrange(H)
        r = rnd.randrange(2, 9)
        md.ellipse([x, y, x + r, y + r], fill=(238, 236, 230))
    marks = marks.filter(ImageFilter.GaussianBlur(2.2))
    return ImageChops.multiply(base, marks)


def _leader(d: ImageDraw.ImageDraw, x1: int, x2: int, y: int) -> None:
    for x in range(x1, x2, 7):
        d.point((x, y), fill=FADE)


def render(stats: dict[str, Any]) -> bytes:
    img = _paper()
    d = ImageDraw.Draw(img)

    f_small = _font(MONO, 20)
    f_mono = _font(MONO, 24)
    f_body = _font(SANS, 27)
    f_name = _font(SANS_BOLD, 62)
    f_sub = _font(SANS, 30)
    f_stamp = _font(SANS_BOLD, 54)
    f_stamp_s = _font(SANS, 20)

    m = 88                            # поля листа
    d.rectangle([m - 26, 64, W - m + 26, H - 64], outline=INK, width=2)

    # --- шапка ---
    d.text((m, 118), "НАБЛЮДАТЕЛЬНЫЙ ПОСТ · ЕДИНСТВЕННЫЙ ЭКЗЕМПЛЯР", font=f_small, fill=FADE)
    d.text((m, 168), "СПРАВКА", font=f_name, fill=INK)
    d.text((m, 244), "о состоянии обратимости", font=f_sub, fill=FADE)
    d.line([m, 300, W - m, 300], fill=INK, width=3)
    d.line([m, 306, W - m, 306], fill=INK, width=1)

    # --- поля ---
    y = 366
    for label, value in stats["fields"]:
        d.text((m, y), label.upper(), font=f_small, fill=FADE)
        w_val = d.textlength(value, font=f_body)
        d.text((W - m - w_val - 4, y - 6), value, font=f_body, fill=INK)
        _leader(d, m + int(d.textlength(label.upper(), font=f_small)) + 14,
                W - m - int(w_val) - 14, y + 12)
        y += 62

    # --- показания ---
    y += 24
    d.line([m, y, W - m, y], fill=INK, width=1)
    y += 34
    d.text((m, y), "ПОСЛЕДНИЕ ПОКАЗАНИЯ", font=f_small, fill=FADE)
    y += 46
    d.rectangle([m, y, m + 4, y + 150], fill=SEAL)
    for line in stats["quote"][:4]:
        d.text((m + 28, y), line, font=f_body, fill=INK)
        y += 40

    # --- подпись и штамп ---
    base = H - 300
    d.line([m, base, m + 320, base], fill=INK, width=1)
    d.text((m, base + 14), "ПОДПИСЬ НАБЛЮДАТЕЛЯ", font=f_small, fill=FADE)
    d.text((m, H - 148), stats["footer"], font=f_small, fill=FADE)

    stamp = Image.new("RGBA", (460, 200), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    sd.rectangle([4, 4, 456, 196], outline=(*SEAL, 235), width=6)
    sd.text((44, 46), stats["verdict"], font=f_stamp, fill=(*SEAL, 235))
    sd.text((48, 128), stats["verdict_note"], font=f_stamp_s, fill=(*SEAL, 200))
    stamp = stamp.rotate(11, expand=True, resample=Image.BICUBIC)
    img.paste(stamp, (W - m - 400, base - 130), stamp)

    out = io.BytesIO()
    # шумная бумага в PNG весит мегабайт, в JPEG — впятеро меньше
    img.save(out, format="JPEG", quality=90, optimize=True, progressive=True)
    return out.getvalue()
