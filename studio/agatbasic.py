# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""
Программа Бейсика-А9 (Агат-9, ИКП) из текста -> файл A для ДОС 3.3.

- Токены - как у Applesoft (Бейсик-А9 - его потомок). Таблица - из DISK
  Commander (dsk_tools, src/bas_tokens.h, Agat_tokens), отличия от Applesoft - в
  графике ($88-$93: GR=, TEXT=, MGR=, HGR=, RIBBON=...).
- Строки, DATA и REM хранятся кодами Агата с перевернутым старшим разрядом:
  латиница и цифры - 7-битный ASCII, заглавная кириллица - $60-$7F, строчная -
  $E0-$FF. При выводе Бейсик разряд возвращает, и на экран идут коды Агата
  (tables.AGAT: заглавная кириллица $E0-$FF, строчная $60-$7F). Проверено в
  eCat3 на ИКП (ikp1-16414).
- Программа лежит с $1901 (TXTTAB Бейсика-А9), строки связаны адресами.

    lines = [(10, 'HOME:PRINT "Привет"'), ...]
    body = a_file(lines)            # тело файла A: длина, программа
"""

import struct

import tables

TXTTAB = 0x1901

# $80... - по таблице Agat_tokens DISK Commander; $ вместо ¤
TOKENS = [
    "END", "FOR", "NEXT", "DATA", "INPUT", "DEL", "DIM", "READ", "GR=", "TEXT=",
    "PR#", "IN#", "CALL", "PLOT", "!", "&", "MGR=", "HGR=", "RIBBON=", "&",
    "DRAW", "XDRAW", "HTAB", "HOME", "ROT=", "SCALE=", "SHLOAD", "TRACE", "NOTRACE", "NORMAL",
    "INVERSE", "FLASH", "COLOR=", "POP", "VTAB", "HIMEM:", "LOMEM:", "ONERR", "RESUME", "RECALL",
    "STORE", "SPEED=", "LET", "GOTO", "RUN", "IF", "RESTORE", "&", "GOSUB", "RETURN",
    "REM", "STOP", "ON", "WAIT", "LOAD", "SAVE", "DEF", "POKE", "PRINT", "CONT",
    "LIST", "CLEAR", "GET", "NEW", "TAB(", "TO", "FN", "SPC(", "THEN", "AT",
    "NOT", "STEP", "+", "-", "*", "/", "^", "AND", "OR", ">",
    "=", "<", "SGN", "INT", "ABS", "USR", "FRE", "SCRN(", "PDL", "POS",
    "SQR", "RND", "LOG", "EXP", "COS", "SIN", "TAN", "ATN", "PEEK", "LEN",
    "STR$", "VAL", "ASC", "CHR$", "LEFT$", "RIGHT$", "MID$",
]
# Поиск - сначала длинные (TEXT= раньше TO, ATN раньше AT); первое вхождение дубля (&)
_KW = sorted(((kw, 0x80 + i) for i, kw in enumerate(TOKENS) if TOKENS.index(kw) == i),
             key=lambda x: -len(x[0]))


def char(ch):
    """Знак в байт программы: код Агата с перевернутым старшим разрядом"""
    if ch not in tables.AGAT:
        raise ValueError("нет знака %r в наборе Агата" % ch)
    return tables.AGAT[ch] ^ 0x80


def tokenize(text):
    """Текст строки (без номера) -> байты. Вне кавычек пробелы убираются, а
    ключевые слова (заглавными) становятся токенами; в кавычках, после REM и в
    DATA (до двоеточия) знаки идут как есть"""
    out = bytearray()
    i, in_str, in_rem, in_data = 0, False, False, False
    while i < len(text):
        ch = text[i]
        if in_rem or in_str or (in_data and ch != ":"):
            out.append(char(ch))
            if in_str and ch == '"':
                in_str = False
            elif in_data and ch == '"':
                in_str = True
            i += 1
            continue
        in_data = False
        if ch == '"':
            in_str = True
            out.append(char(ch))
            i += 1
            continue
        if ch == " ":
            i += 1
            continue
        for kw, tok in _KW:
            if text.startswith(kw, i):
                out.append(tok)
                i += len(kw)
                in_rem = kw == "REM"
                in_data = kw == "DATA"
                break
        else:
            out.append(char(ch))
            i += 1
    return bytes(out)


def program(lines, base=TXTTAB):
    """[(номер, текст)] -> байты программы с адреса base (строки связаны)"""
    body = bytearray()
    addr = base
    for num, text in lines:
        toks = tokenize(text)
        nxt = addr + 4 + len(toks) + 1
        body += struct.pack("<HH", nxt, num) + toks + b"\x00"
        addr = nxt
    return bytes(body + b"\x00\x00")


def a_file(lines):
    """Тело файла A (Бейсик) для ДОС: длина программы, программа"""
    p = program(lines)
    return struct.pack("<H", len(p)) + p


def detokenize(body):
    """Тело файла A -> текст (для проверки)"""
    rev = {v: k for k, v in tables.AGAT.items() if k not in "Ёё"}
    n = body[0] | (body[1] << 8)
    p = body[2:2 + n]
    out, i = [], 0
    while i + 4 <= len(p):
        link, num = struct.unpack("<HH", p[i:i + 4])
        if link == 0:
            break
        j = p.index(0, i + 4)
        s = []
        for b in p[i + 4:j]:
            s.append(TOKENS[b - 0x80] if 0x80 <= b < 0x80 + len(TOKENS) and not _in_str(s)
                     else rev.get(b ^ 0x80, "?"))
        out.append("%d %s" % (num, "".join(s)))
        i = j + 1
    return out


def _in_str(s):
    return "".join(s).count('"') % 2 == 1
