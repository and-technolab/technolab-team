#!/usr/bin/env python3
"""Типографика HTML по правилам ТехноЛаба.

Usage: python3 typography.py check|fix <deck.html> [...]

Склеивает короткие слова и дефисы только в тексте, сохраняя разметку и код.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP = {"style", "script", "svg", "title", "code", "pre", "textarea", "kbd"}
INLINE = {"a", "b", "i", "em", "strong", "span", "small", "sup", "sub", "mark", "abbr",
          "time", "u", "s", "q", "cite", "dfn", "var", "bdi", "bdo", "data", "label"}
NB, NBH = " ", "‑"

TOKEN = re.compile(r"(<!--.*?-->|<[^>]+>)", re.S)
TAG = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9-]*)")
WORD = r"[^\W_]{1,3}"
# перед коротким словом — не буква и не цифра, не дефис и не хвост сущности (&amp; &#160;)
START = r"(?<![\w\-‑&#])"
SHORT = re.compile(START + rf"({WORD}) (?=[^\s<])")
HYPHEN = re.compile(START + rf"({WORD})-(?=[^\W_])")
ENDS_SPACE = re.compile(START + rf"{WORD} $")
# перед <br> — только целое слово: в начале текста, после пробела или открывающей кавычки и скобки
# («10:00<br>» — не короткое слово «00»)
ENDS_WORD = re.compile(r'(?<![^\s\u00a0«„"(\[])' + WORD + r"[ \u00a0]?$")


def _ctx(text: str, at: int, width: int = 28) -> str:
    s = text[max(0, at - width):at + width].replace(NB, "·").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


def _tag(token: str) -> tuple[bool, str] | None:
    if token.startswith("<!--"):
        return None
    m = TAG.match(token)
    return (m.group(1) == "/", m.group(2).lower()) if m else None


def bind(html: str, report: list[tuple[str, str]] | None = None) -> str:
    """Вернуть HTML со склейкой. В report складываются находки: что склеено и что — руками."""
    parts = TOKEN.split(html)
    out: list[str] = []
    skip: str | None = None
    tail_short = False  # предыдущий текст кончился коротким словом без пробела, дальше только строчные теги

    for i, part in enumerate(parts):
        if i % 2 == 1:  # тег или комментарий
            tag = _tag(part)
            if tag:
                closing, name = tag
                if skip:
                    if closing and name == skip:
                        skip = None
                elif not closing and name in SKIP and not part.rstrip().endswith("/>"):
                    skip = name
                if name not in INLINE:
                    tail_short = False
            out.append(part)
            continue

        if skip or not part:
            out.append(part)
            continue

        text = part.replace("&nbsp;", NB).replace("&#160;", NB).replace("&#8209;", NBH)

        if tail_short and text[:1] == " " and len(text) > 1 and not text[1].isspace():
            if report is not None:
                report.append(("склеить", _ctx(text, 0)))
            text = NB + text[1:]
        tail_short = False

        for m in SHORT.finditer(text):
            if report is not None:
                report.append(("склеить", _ctx(text, m.end())))
        text = SHORT.sub(lambda m: m.group(1) + NB, text)
        for m in HYPHEN.finditer(text):
            if report is not None:
                report.append(("склеить", _ctx(text, m.end())))
        text = HYPHEN.sub(lambda m: m.group(1) + NBH, text)

        nxt = _tag(parts[i + 1]) if i + 1 < len(parts) else None
        if nxt:
            closing, name = nxt
            if not closing and ENDS_SPACE.search(text):
                if name in INLINE:
                    if report is not None:
                        report.append(("склеить", _ctx(text, len(text))))
                    text = text[:-1] + NB
                elif report is not None:
                    kind = "руками: перед <br>" if name == "br" else f"руками: перед <{name}>"
                    report.append((kind, _ctx(text, len(text))))
            elif not closing and name == "br" and ENDS_WORD.search(text) and report is not None:
                report.append(("руками: перед <br>", _ctx(text, len(text))))
            elif closing and name in INLINE and re.search(START + WORD + "$", text):
                tail_short = True

        out.append(text.replace(NB, "&nbsp;").replace(NBH, "&#8209;"))

    return "".join(out)


def scan(html: str) -> list[tuple[str, str]]:
    """Находки без изменения файла: что склеил бы fix и что придётся править руками."""
    report: list[tuple[str, str]] = []
    bind(html, report)
    return report


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("check", "fix"):
        print(__doc__.strip().split("\n\n")[1])
        return 2
    mode, bad = argv[1], 0
    for name in argv[2:]:
        path = Path(name)
        html = path.read_text(encoding="utf-8")
        report: list[tuple[str, str]] = []
        fixed = bind(html, report)
        glued = [c for k, c in report if k == "склеить"]
        manual = [(k, c) for k, c in report if k != "склеить"]
        if mode == "fix":
            if fixed != html:
                path.write_text(fixed, encoding="utf-8")
            print(f"{path.name}: склеено {len(glued)}, руками {len(manual)}")
        else:
            print(f"{path.name}: склеить {len(glued)}, руками {len(manual)}")
            for c in glued[:12]:
                print(f"  склеить   … {c} …")
        for k, c in manual:
            print(f"  {k}   … {c} …")
        bad += len(manual) + (len(glued) if mode == "check" else 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
