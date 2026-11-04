"""Подмножество LilyPond для entertainer.ly: \\relative, аккорды, лиги, \\repeat
volta с \\alternative, << {A} \\\\ {B} >> (берется голос A). Выход: события
(начало в долях, длина в долях, [высоты MIDI], номер вольты/повтора)."""
import re

STEP = {"c": 0, "d": 1, "e": 2, "f": 3, "g": 4, "a": 5, "b": 6}
SEMI = [0, 2, 4, 5, 7, 9, 11]


def clean(text):
    text = re.sub(r"%[^\n]*", "", text)
    text = re.sub(r"[\^_-]?\\markup\s*\{[^{}]*\}", " ", text)
    text = re.sub(r"\\once", " ", text)
    text = re.sub(r"\\(override|revert)\s+\w+\s+#'[\w-]+(\s*=\s*#+[\w-]+)?", " ", text)
    text = re.sub(r"#\(set-octavation\s+-?\d\)", " ", text)
    text = re.sub(r'\\change\s+Staff\s*=\s*"\w+"', " ", text)
    text = re.sub(r"\\key\s+\w+\s+\\\w+", " ", text)
    text = re.sub(r"\\time\s+\d+/\d+", " ", text)
    text = re.sub(r"\\clef\s+\w+", " ", text)
    text = re.sub(r'\\bar\s+"[^"]*"', " ", text)
    text = re.sub(r"\\(stemUp|stemDown|stemNeutral|break|blanknotes|unblanknotes)\b", " ", text)
    text = re.sub(r"[-^_]\\[a-zA-Z!<>]+|[-^_][()\[\]^.>]|\\!|\\[<>]", " ", text)
    text = re.sub(r"\*\d+/\d+", "", text)
    text = re.sub(r"\\(ppp|pp|p|mp|mf|f|ff|fff|fz|sf|sfz)(?![a-z])", " ", text)
    return text


TOK = re.compile(r"~|<<|>>|\\\\|\\repeat|\\alternative|volta|\{|\}|<[^<>]*>[\d.]*~?|"
                 r"[a-g](?:isis|eses|is|es|s)?[',]*!?[\d.]*~?|[rs][\d.]*|\||\d+")


def note_pitch(tok, ref):
    """Высота по относительному правилу; ref = (ступень, MIDI)"""
    m = re.match(r"([a-g])((?:isis|eses|is|es|s)?)([',]*)", tok)
    name, acc, octs = m.groups()
    alt = {"": 0, "is": 1, "es": -1, "s": -1, "isis": 2, "eses": -2}[acc]
    rstep, rmidi = ref
    roct = rmidi // 12 if rmidi is not None else 4
    # абсолютная ступень ref
    rabs = roct * 7 + rstep
    best = None
    for o in range(roct - 2, roct + 3):
        a = o * 7 + STEP[name]
        if abs(a - rabs) <= 3:
            best = a
            break
    if best is None:
        best = rabs
    best += 7 * (octs.count("'") - octs.count(","))
    o, st = divmod(best, 7)
    midi = o * 12 + SEMI[st] + alt
    return (st, midi), midi


def dur_of(s, prev):
    m = re.match(r"(\d+)(\.*)", s)
    if not m:
        return prev
    d = 4.0 / int(m.group(1))
    add = d
    for _ in m.group(2):
        add /= 2
        d += add
    return d


def parse(text, start_ref):
    """-> дерево: список узлов ("n", длина, [MIDI], лига) | ("rep", тело, [вольты])"""
    toks = TOK.findall(clean(text))
    pos = 0
    ref = [start_ref]
    dur = [1.0]

    def seq(stop):
        nonlocal pos
        out = []
        while pos < len(toks):
            t = toks[pos]
            if t == stop:
                pos += 1
                return out
            pos += 1
            if t == "~":
                if out and out[-1][0] == "n":
                    out[-1] = out[-1][:3] + (True,)
            elif t == "{":
                out.extend(seq("}"))
            elif t == "\\repeat":
                assert toks[pos] == "volta"
                pos += 2                       # volta N
                assert toks[pos] == "{"
                pos += 1
                body = seq("}")
                alts = []
                if pos < len(toks) and toks[pos] == "\\alternative":
                    pos += 1
                    assert toks[pos] == "{"
                    pos += 1
                    while toks[pos] == "{":
                        pos += 1
                        alts.append(seq("}"))
                    assert toks[pos] == "}"
                    pos += 1
                out.append(("rep", body, alts))
            elif t == "<<":
                # голос A, затем пропустить остальные до >>
                assert toks[pos] == "{"
                pos += 1
                # Каждый голос - от ноты перед <<; после >> отсчет идет от
                # последней ноты последнего голоса. Берется голос A, нужны
                # только высоты остальных
                save = ref[0]
                a = seq("}")
                while toks[pos] == "\\\\":
                    pos += 1
                    assert toks[pos] == "{"
                    pos += 1
                    ref[0] = save
                    seq("}")      # длительность по умолчанию - из текста, как у LilyPond
                assert toks[pos] == ">>", toks[pos]
                pos += 1
                out.extend(a)
            elif t.startswith("<"):
                body = t[1:t.index(">")]
                tail = t[t.index(">") + 1:]
                tie = tail.endswith("~")
                d = dur_of(tail.rstrip("~"), dur[0])
                dur[0] = d
                ps = []
                r = ref[0]
                first = None
                for nt in body.split():
                    r, mid = note_pitch(nt, r)
                    if first is None:
                        first = r
                    ps.append(mid)
                ref[0] = first
                out.append(("n", d, ps, tie))
            elif t[0] in "abcdefg":
                m = re.match(r"([a-g](?:isis|eses|is|es|s)?[',]*)!?([\d.]*)(~?)", t)
                ref[0], mid = note_pitch(m.group(1), ref[0])
                d = dur_of(m.group(2), dur[0])
                dur[0] = d
                out.append(("n", d, [mid], m.group(3) == "~"))
            elif t[0] in "rs":
                d = dur_of(t[1:], dur[0])
                dur[0] = d
                out.append(("n", d, [], False))
            # «|», числа - пропуск
        return out

    return seq(None)


def unfold(tree, repeats=None):
    """Повторы развернуть: тело+вольта1, тело+вольта2 ... repeats[i] = False -
    i-й по счету повтор сыграть один раз (тело + последняя вольта)"""
    out = []
    k = [0]

    def walk(nodes):
        for nd in nodes:
            if nd[0] == "n":
                out.append(nd)
            else:
                i = k[0]
                k[0] += 1
                _, body, alts = nd
                twice = True if repeats is None else repeats[i]
                if twice:
                    walk(body)
                    if alts:
                        walk(alts[0])
                    walk(body)
                    if alts:
                        walk(alts[-1])
                else:
                    walk(body)
                    if alts:
                        walk(alts[-1])
    walk(tree)
    return out


def events(nodes):
    """Узлы -> [(начало, длина, [MIDI])], лиги склеены"""
    t = 0.0
    ev = []
    open_tie = None
    for _, d, ps, tie in nodes:
        if ps:
            if open_tie is not None and ev[open_tie][2] == ps:
                s, l, p = ev[open_tie]
                ev[open_tie] = (s, l + d, p)
            else:
                ev.append((t, d, ps))
            open_tie = len(ev) - 1 if tie else None
        else:
            open_tie = None
        t += d
    return ev, t
