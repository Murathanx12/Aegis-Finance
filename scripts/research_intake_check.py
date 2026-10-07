"""research_intake_check -- validate the research-intake CARDS and keep their INDEX current.

`docs/research_intake/cards/<slug>.md` holds one research note per topic or paper; the routine
and the card template are in `docs/research_intake/README.md`. Cards arrive from parallel
sessions, and until this script nothing read them except the next human. A card with no
verdict, an unfilled template placeholder, a hyp_lab family outside the taxonomy or a
machine-specific path was found only when someone tried to act on it. This is the cheap check,
and `docs/research_intake/INDEX.md` is the one table a session reads instead of opening every
card.

Stdlib only and no imports from `backend`: this is tooling, not a runtime service. The hyp_lab
family vocabulary is read from `backend/config.py` with `ast` (`literal_eval` of the assigned
tuple and dict), never by importing the config, so running the checker has no side effects.
`backend/tests/test_research_intake_check.py` pins the parsed tuple to
`backend.config.HYP_LAB_FAMILIES`. If that assignment ever stops being a static literal, the
checker REFUSES with exit 2 instead of guessing.

Usage:
    python -m scripts.research_intake_check                # per-card findings + summary line
    python -m scripts.research_intake_check --write-index  # also (re)write INDEX.md
    python -m scripts.research_intake_check --check-index  # exit 1 if INDEX.md is stale/missing
    python -m scripts.research_intake_check --json         # machine-readable findings
    overrides (tests): --cards-dir DIR  --config PATH  --index PATH  --repo-root DIR

Exit code: 0 when no card has an ERROR (and, with --check-index, INDEX.md is current); 1
otherwise; 2 when the check cannot run (cards dir missing, vocabulary unreadable). A check that
did not run is not a check that passed.

Decisions a reader should know before changing a rule:

* VERDICT. The first line of `## Verdict` declares the verdict: one vocabulary word written as
  `WORD`, `WORD.`, `**WORD**` or `**WORD.**`. A line such as `**NEEDS_DATA is the wrong label
  here**` is NOT a NEEDS_DATA verdict, because it starts with an explanation and not a
  declaration. A parser that accepted any line beginning with the word could not tell the
  explanation from an instance (CLAUDE.md protocol 10). TWO verdicts means the declaration
  joins a second word ("READY_TO_CELL | NEEDS_DATA", the template copied unfilled) or another
  line in the section is nothing but a verdict word. A card may also put another vocabulary
  word in **bold** later in its justification, to give a sub-construction its own status. That
  is a split verdict. It is allowed, and the index shows it as `(+WORD)` so that a reader
  scanning the index for ALREADY_CLOSED does not miss it.
* YEARS. The source year range comes only from `(YYYY)` and `(YYYYa)` inside `## Citation`.
  ISO dates such as `(2026-10-07; ...)` are verification stamps, not publication years.
* DUPLICATE DOIs. Only DOIs in `## Citation` (the card's own sources) are compared across
  cards. The standing decay references (McLean & Pontiff 2016, Harvey-Liu-Zhu 2016) appear in
  other sections of many cards by design, so they are not compared.
* LINE ENDINGS. Cards and INDEX.md are compared after CRLF -> LF normalisation. A Windows
  checkout with autocrlf is not "stale", because a byte gate on line endings is a gate on
  checkout settings (the family of CLAUDE.md protocol 7, already paid for once by
  `.gitattributes`). The index is always WRITTEN with LF and holds no timestamp, so identical
  cards give identical bytes.
* The index holds no warnings and no filesystem state (a missing tracked path is only a
  warning). The same cards give the same INDEX.md on every checkout.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import difflib
import json
import os
import re
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CARDS_DIR = REPO_ROOT / "docs" / "research_intake" / "cards"
DEFAULT_CONFIG = REPO_ROOT / "backend" / "config.py"
INDEX_FILENAME = "INDEX.md"
REGENERATE_CMD = "python -m scripts.research_intake_check --write-index"

# ----------------------------------------------------------------------------- the contract
# The template order. `backend/tests/test_research_intake_check.py` pins this tuple to the
# fenced template in docs/research_intake/README.md, so the two cannot drift apart silently.
REQUIRED_HEADINGS: tuple[str, ...] = (
    "Index fields",
    "Citation",
    "The claim, in one sentence",
    "Mechanism: why the inefficiency could exist, and who is on the other side",
    "Assumptions",
    "Measurable variables: the precursor observable BEFORE the move",
    "Sample period and markets",
    "Effect size as published",
    "Known failure modes and post-publication decay",
    "What AEGIS has on disk to test it",
    "The falsifiable question and the declared primary metric, with costs",
    "Whether a corpse already exists here",
    "hyp_lab family",
    "Verdict",
    "needs_evidence",
)
H_INDEX, H_CITATION, H_DATASET = REQUIRED_HEADINGS[0], REQUIRED_HEADINGS[1], REQUIRED_HEADINGS[9]
H_FAMILY, H_VERDICT, H_NEEDS = REQUIRED_HEADINGS[12], REQUIRED_HEADINGS[13], REQUIRED_HEADINGS[14]

INDEX_KEYS: tuple[str, ...] = ("topic", "mechanism_class", "dataset_status")
MECHANISM_CLASSES: tuple[str, ...] = (
    "information_asymmetry", "risk_premium", "limits_to_arbitrage", "behavioural_bias",
    "estimation_error", "structural_friction", "methodology")
DATASET_STATUSES: tuple[str, ...] = (
    "TRACKED_IN_GIT", "DOCUMENTED_NOT_TRACKED", "NOT_FOUND", "NOT_REQUIRED")
VERDICTS: tuple[str, ...] = (
    "READY_TO_CELL", "NEEDS_DATA", "ALREADY_CLOSED", "NOT_A_HYPOTHESIS_YET")
NEEDS_EVIDENCE_MIN, NEEDS_EVIDENCE_MAX = 1, 3
#: a backticked path under one of these must exist in the checkout (else a WARNING). Data
#: under backend/data/ is deliberately absent: a cloud checkout lacks gitignored data.
TRACKED_PREFIXES: tuple[str, ...] = (
    "docs/", "scripts/", "backend/services/", "backend/tests/", ".claude/")

FAMILIES_NAME = "HYP_LAB_FAMILIES"
ALIASES_NAME = "HYP_LAB_FAMILY_ALIASES"
UNMAPPED_NAME = "HYP_LAB_UNMAPPED_FAMILY"
DEFAULT_UNMAPPED = "family_unmapped"

ERROR, WARNING = "error", "warning"

# ----------------------------------------------------------------------------- patterns
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_TITLE_RE = re.compile(r"^CARD:\s*(.*?)\s*$")
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)
_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d{1,9}[.)])(?:[ \t]+(.*))?$")
#: `- topic: X`, also `- **topic:** X` / `- `topic`: X`; the key ends at the FIRST colon
_KEY_VALUE_RE = re.compile(r"^[*`]*([A-Za-z_][A-Za-z0-9_ ]*?)[*`]*\s*:[*`]*\s*(.*)$")
#: the controlled value at the start of a field; a trailing note ("NOT_FOUND (not pulled)") is
#: allowed and ignored, a second controlled value is not
_LEAD_TOKEN_RE = re.compile(r"^[`*]*([A-Za-z_]+)[`*]*(?=$|[\s(;,.:\u2014\u2013-])")

_V_ALT = "|".join(VERDICTS)
#: the four accepted declaration forms, at the very start of the verdict line
_VERDICT_DECL_RE = re.compile(
    rf"^\s*(?:\*\*(?P<bold>{_V_ALT})\.?\*\*|(?P<plain>{_V_ALT})\.?(?![A-Za-z0-9_]))")
#: a second word JOINED to the declaration: "A | B", "A / B", "A, B", "A or B", "A and B"
_VERDICT_JOINED_RE = re.compile(
    rf"^\s*(?:[|/,+&]|or\b|and\b)\s*(?:\*\*)?(?:{_V_ALT})(?![A-Za-z0-9_])")
#: a line that is NOTHING but a verdict word: a second declaration
_VERDICT_ONLY_LINE_RE = re.compile(rf"^\s*(?:\*\*)?(?:{_V_ALT})\.?(?:\*\*)?\s*$")
#: a vocabulary word in bold anywhere in the justification: a split verdict
_VERDICT_BOLD_RE = re.compile(rf"\*\*({_V_ALT})\.?\*\*")

_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>`]+")
_YEAR_RE = re.compile(r"\((1[6-9]\d\d|20\d\d)[a-z]?\)")
_TBD_RE = re.compile(r"\b(TBD|TODO)s?\b")
#: `<word ...>` that opens on a letter, is not glued to a preceding word ("N<T" is maths),
#: and closes on a non-space; HTML tags and autolinks are filtered out after matching.
_ANGLE_RE = re.compile(r"(?<![A-Za-z0-9_])<([A-Za-z][^<>\n]*?)(?<!\s)>")
_HTML_TAG_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)(?:\s[^<>]*)?/?$")
_HTML_TAGS = frozenset(
    "a abbr b blockquote br cite code dd del details div dl dt em h1 h2 h3 h4 h5 h6 hr i img "
    "ins kbd li mark ol p pre q s samp section small span strong sub summary sup table tbody "
    "td th thead tr u ul var".split())
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_HOME_RE = re.compile(r"^~(?:$|[\\/]|[A-Za-z_][\w.-]*[\\/])")
_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
_POSIX_ROOTS = frozenset(
    "home Users root tmp mnt media var opt usr etc srv Volumes private workspace workspaces "
    "Applications".split())
_PATTERN_CHARS = set("*?[]{}<>$%")


# ----------------------------------------------------------------------------- vocabulary
class VocabError(RuntimeError):
    """The family vocabulary could not be read statically; the check must not run."""


@dataclass(frozen=True)
class FamilyVocab:
    families: tuple[str, ...]
    aliases: dict[str, str]
    unmapped: str
    source: str


def load_family_vocab(config_path: Path) -> FamilyVocab:
    """Read the hyp_lab family vocabulary from `config_path` WITHOUT importing it.

    Module-level assignments only, last one wins (as at import). An augmented assignment or a
    non-literal value is REFUSED (`VocabError`): a vocabulary this cannot read statically is not
    one it may guess.
    """
    try:
        src = Path(config_path).read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(config_path))
    except (OSError, UnicodeDecodeError, SyntaxError) as e:
        raise VocabError(f"cannot read {config_path}: {type(e).__name__}: {e}") from e
    wanted = (FAMILIES_NAME, ALIASES_NAME, UNMAPPED_NAME)
    nodes: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in wanted:
                    nodes[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in wanted and node.value is not None:
                nodes[node.target.id] = node.value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if node.target.id in wanted:
                raise VocabError(f"{node.target.id} is modified by an augmented assignment at "
                                 f"line {node.lineno} of {config_path}; cannot read it statically")
    if FAMILIES_NAME not in nodes:
        raise VocabError(f"{FAMILIES_NAME} is not assigned at module level in {config_path}")

    def _literal(name: str) -> object:
        try:
            return ast.literal_eval(nodes[name])
        except ValueError as e:
            raise VocabError(f"{name} in {config_path} is not a static literal ({e}); "
                             "cannot read it without importing the config") from e

    families = _literal(FAMILIES_NAME)
    if (not isinstance(families, (tuple, list)) or not families
            or not all(isinstance(f, str) and f for f in families)):
        raise VocabError(f"{FAMILIES_NAME} in {config_path} is not a non-empty tuple of strings")
    aliases = _literal(ALIASES_NAME) if ALIASES_NAME in nodes else {}
    if not isinstance(aliases, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in aliases.items()):
        raise VocabError(f"{ALIASES_NAME} in {config_path} is not a dict of strings")
    unmapped = _literal(UNMAPPED_NAME) if UNMAPPED_NAME in nodes else DEFAULT_UNMAPPED
    if not isinstance(unmapped, str) or not unmapped:
        raise VocabError(f"{UNMAPPED_NAME} in {config_path} is not a non-empty string")
    return FamilyVocab(tuple(families), dict(aliases), unmapped, str(config_path))


# ----------------------------------------------------------------------------- data model
@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "line": self.line,
                "message": self.message}


@dataclass
class Line:
    no: int
    text: str
    fenced: bool


@dataclass
class Section:
    heading: str
    line: int
    body: list[Line]


@dataclass
class Span:
    text: str
    line: int


@dataclass
class Card:
    path: Path
    text: str = ""
    slug: str | None = None
    topic: str | None = None
    mechanism_class: list[str] = field(default_factory=list)
    dataset_status: str | None = None
    family: str | None = None
    family_written: str | None = None
    verdict: str | None = None
    verdict_also: list[str] = field(default_factory=list)
    needs_evidence: list[str] = field(default_factory=list)
    dois: list[str] = field(default_factory=list)
    years: tuple[int, int] | None = None
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, line: int | None = None) -> None:
        self.findings.append(Finding(level, code, message, line))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNING]

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.slug or self.path.stem, self.path.name)


# ----------------------------------------------------------------------------- markdown
def _scan_lines(text: str) -> tuple[list[Line], int | None]:
    """Every line, flagged when it is inside a fenced code block (CommonMark-ish).

    Returns the line of a fence that never closes, because an unclosed fence hides the rest
    of the card from every check, which is a finding in itself.
    """
    out: list[Line] = []
    fence: str | None = None
    opened_at: int | None = None
    for no, raw in enumerate(text.split("\n"), 1):
        if fence is None:
            m = _FENCE_OPEN_RE.match(raw)
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence, opened_at = m.group(1), no
                out.append(Line(no, raw, True))
            else:
                out.append(Line(no, raw, False))
        else:
            m = _FENCE_CLOSE_RE.match(raw)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append(Line(no, raw, True))
    return out, (opened_at if fence is not None else None)


def _norm_heading(h: str) -> str:
    return " ".join(h.replace("*", "").replace("`", "").split()).casefold()


_REQUIRED_BY_NORM = {_norm_heading(h): h for h in REQUIRED_HEADINGS}


def _paragraphs(lines: list[Line]) -> list[list[Line]]:
    paras: list[list[Line]] = []
    cur: list[Line] = []
    for ln in lines:
        if ln.fenced or not ln.text.strip():
            if cur:
                paras.append(cur)
                cur = []
            continue
        cur.append(ln)
    if cur:
        paras.append(cur)
    return paras


def _code_and_prose(lines: list[Line]) -> tuple[list[Span], list[tuple[int, str]]]:
    """Inline code spans (paragraph-scoped, so a span may wrap a line) and the prose with
    every span blanked out. Fenced blocks contribute to neither."""
    spans: list[Span] = []
    prose: list[tuple[int, str]] = []
    for para in _paragraphs(lines):
        joined = "\n".join(ln.text for ln in para)
        starts: list[int] = []
        off = 0
        for ln in para:
            starts.append(off)
            off += len(ln.text) + 1
        chars = list(joined)
        for m in _CODE_SPAN_RE.finditer(joined):
            line_no = para[bisect.bisect_right(starts, m.start()) - 1].no
            spans.append(Span(m.group(2).replace("\n", " ").strip(), line_no))
            for i in range(m.start(), m.end()):
                if chars[i] != "\n":
                    chars[i] = " "
        for ln, txt in zip(para, "".join(chars).split("\n")):
            prose.append((ln.no, txt))
    return spans, prose


def _raw_text(lines: list[Line]) -> str:
    return "\n".join(ln.text for ln in lines if not ln.fenced)


def _close(word: str, vocab: tuple[str, ...] | list[str]) -> str:
    m = difflib.get_close_matches(word, list(vocab), n=1, cutoff=0.6)
    return f" (did you mean `{m[0]}`?)" if m else ""


# ----------------------------------------------------------------------------- one card
def parse_card(path: Path, vocab: FamilyVocab, repo_root: Path = REPO_ROOT) -> Card:
    """Parse and check ONE card. Cross-card checks (duplicates) live in `check_cards`."""
    card = Card(path=Path(path))
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        card.add(ERROR, "read-error", f"not valid UTF-8 ({e})")
        return card
    except OSError as e:
        card.add(ERROR, "read-error", f"cannot read: {type(e).__name__}: {e}")
        return card
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    card.text = text

    lines, unclosed = _scan_lines(text)
    if unclosed is not None:
        card.add(WARNING, "fence-unclosed",
                 "code fence never closes, so everything after it is invisible to the checks",
                 unclosed)

    title: tuple[int, str] | None = None
    first_content: int | None = None
    preamble: list[Line] = []
    sections: list[Section] = []
    for ln in lines:
        if first_content is None and ln.text.strip():
            first_content = ln.no
        m = None if ln.fenced else _ATX_RE.match(ln.text)
        if m and len(m.group(1)) == 1 and title is None and not sections:
            title = (ln.no, (m.group(2) or "").strip())
            continue
        if m and len(m.group(1)) == 2:
            sections.append(Section((m.group(2) or "").strip(), ln.no, []))
            continue
        (sections[-1].body if sections else preamble).append(ln)

    _check_title(card, title, first_content)
    found = _check_headings(card, sections)

    def body(h: str) -> list[Line]:
        return found[h].body if h in found else []

    _check_index_fields(card, body(H_INDEX), found.get(H_INDEX))
    _check_citation(card, body(H_CITATION), found.get(H_CITATION))
    _check_family(card, body(H_FAMILY), found.get(H_FAMILY), vocab)
    _check_verdict(card, body(H_VERDICT), found.get(H_VERDICT))
    _check_needs_evidence(card, body(H_NEEDS), found.get(H_NEEDS))

    dataset = found.get(H_DATASET)
    dataset_lines = {ln.no for ln in dataset.body} if dataset else set()
    title_line = [Line(title[0], lines[title[0] - 1].text, False)] if title else []
    all_spans: list[Span] = []
    all_prose: list[tuple[int, str]] = []
    for chunk in [title_line, preamble] + [s.body for s in sections]:
        spans, prose = _code_and_prose(chunk)
        all_spans += spans
        all_prose += prose
    for s in sections:                   # a placeholder in a heading is still a placeholder
        all_prose.append((s.line, s.heading))
    _check_placeholders(card, all_prose, dataset_lines)
    _check_paths(card, all_spans, Path(repo_root))
    return card


def _check_title(card: Card, title: tuple[int, str] | None, first_content: int | None) -> None:
    if title is None:
        card.add(ERROR, "title-missing", "no `# CARD: <slug>` title line")
        return
    line, htext = title
    m = _TITLE_RE.match(htext)
    if not m or not m.group(1).strip("` "):
        card.add(ERROR, "title-missing",
                 f"first H1 is `# {htext}`, not `# CARD: <slug>`", line)
        return
    if first_content is not None and first_content < line:
        card.add(WARNING, "title-position", "content precedes the `# CARD:` title", line)
    card.slug = m.group(1).strip().strip("`").strip()
    if card.slug != card.path.stem:
        card.add(ERROR, "slug-mismatch",
                 f"title slug `{card.slug}` does not equal the filename stem "
                 f"`{card.path.stem}`", line)


def _check_headings(card: Card, sections: list[Section]) -> dict[str, Section]:
    found: dict[str, Section] = {}
    extras: list[Section] = []
    order: list[tuple[int, Section]] = []
    for s in sections:
        canon = _REQUIRED_BY_NORM.get(_norm_heading(s.heading))
        if canon is None:
            extras.append(s)
        elif canon in found:
            card.add(ERROR, "heading-duplicate",
                     f"`## {canon}` appears again (first at line {found[canon].line})", s.line)
        else:
            found[canon] = s
            order.append((REQUIRED_HEADINGS.index(canon), s))
    for h in REQUIRED_HEADINGS:
        if h not in found:
            near = difflib.get_close_matches(
                _norm_heading(h), [_norm_heading(e.heading) for e in extras], n=1, cutoff=0.5)
            hint = ""
            if near:
                e = next(x for x in extras if _norm_heading(x.heading) == near[0])
                hint = f" (closest present heading: `## {e.heading}` at line {e.line})"
            card.add(ERROR, "heading-missing", f"required heading `## {h}` not found{hint}")
    best = -1
    best_heading = ""
    for idx, s in order:
        if idx < best:
            card.add(WARNING, "heading-order",
                     f"`## {REQUIRED_HEADINGS[idx]}` comes after `## {best_heading}`; "
                     "the template puts it before", s.line)
        elif idx > best:
            best, best_heading = idx, REQUIRED_HEADINGS[idx]
    return found


def _bullets(lines: list[Line]) -> list[tuple[int, str]]:
    """Top-level bullets with their continuation lines folded in: [(line, text)].

    A line directly under an item continues it (a wrapped value, a nested bullet). After a
    blank line only an INDENTED line does; an unindented paragraph ends the list, so a note
    under `- dataset_status: NOT_FOUND` is not read as part of the value.
    """
    out: list[list] = []
    base: int | None = None
    state = "none"                       # "lazy" | "indented" | "none"
    for ln in lines:
        if ln.fenced:
            state = "none"
            continue
        text = ln.text
        if not text.strip():
            if state == "lazy":
                state = "indented"
            continue
        m = _BULLET_RE.match(text)
        if m:
            indent = len(m.group(1).expandtabs(4))
            if base is None:
                base = indent
            if indent <= base:
                out.append([ln.no, (m.group(2) or "").strip()])
                state = "lazy"
                continue
        indented = len(text) - len(text.lstrip()) >= 2
        if out and (state == "lazy" or (state == "indented" and indented)):
            out[-1][1] = (out[-1][1] + " " + text.strip()).strip()
            state = "lazy"
        else:
            state = "none"
    return [(no, txt) for no, txt in out]


def _check_index_fields(card: Card, lines: list[Line], sec: Section | None) -> None:
    if sec is None:
        return
    seen: dict[str, tuple[int, str]] = {}
    for no, item in _bullets(lines):
        m = _KEY_VALUE_RE.match(item)
        if not m:
            card.add(WARNING, "index-field-unknown",
                     f"bullet is not `key: value`: {item[:60]!r}", no)
            continue
        key, value = m.group(1).strip().lower(), m.group(2).strip()
        if key not in INDEX_KEYS:
            card.add(WARNING, "index-field-unknown",
                     f"unknown index field `{key}`{_close(key, INDEX_KEYS)}", no)
            continue
        if key in seen:
            card.add(ERROR, "index-field-duplicate",
                     f"`{key}` given twice (first at line {seen[key][0]})", no)
            continue
        seen[key] = (no, value)
    for key in INDEX_KEYS:
        if key not in seen:
            card.add(ERROR, "index-field-missing",
                     f"`## Index fields` has no `- {key}:` bullet", sec.line)

    if "topic" in seen:
        no, value = seen["topic"]
        if not value.strip("`* "):
            card.add(ERROR, "index-field-invalid", "`topic` is empty", no)
        else:
            card.topic = value
    if "mechanism_class" in seen:
        no, value = seen["mechanism_class"]
        items = [v.strip() for v in re.sub(r"\([^()]*\)", " ", value).split(",")]
        items = [v for v in items if v.strip("`* ")]
        if not items:
            card.add(ERROR, "index-field-invalid", "`mechanism_class` is empty", no)
        good: list[str] = []
        for v in items:
            lead = _LEAD_TOKEN_RE.match(v)
            canon = lead.group(1).casefold() if lead else None
            if canon not in MECHANISM_CLASSES:
                shown = v.strip("`* ")
                card.add(ERROR, "index-field-invalid",
                         f"mechanism_class `{shown}` is not one of {', '.join(MECHANISM_CLASSES)}"
                         f"{_close(shown.casefold(), MECHANISM_CLASSES)}", no)
            elif canon in good:
                card.add(WARNING, "index-field-duplicate",
                         f"mechanism_class `{canon}` listed twice", no)
            else:
                good.append(canon)
        card.mechanism_class = good
    if "dataset_status" in seen:
        no, value = seen["dataset_status"]
        v = value.strip()
        named = {s for s in DATASET_STATUSES
                 if re.search(rf"(?<![A-Z_]){s}(?![A-Z_])", v.upper())}
        lead = _LEAD_TOKEN_RE.match(v)
        tok = lead.group(1).upper() if lead else ""
        if tok in DATASET_STATUSES and named == {tok}:
            card.dataset_status = tok
        elif len(named) > 1:
            card.add(ERROR, "index-field-invalid",
                     f"dataset_status must be exactly ONE value, got {v!r}", no)
        else:
            shown = v.strip("`* ")
            card.add(ERROR, "index-field-invalid",
                     f"dataset_status `{shown}` is not one of {' | '.join(DATASET_STATUSES)}"
                     f"{_close(shown.upper(), DATASET_STATUSES)}", no)


def normalise_doi(raw: str) -> str:
    """Lower-case `10.x/y`, with trailing prose punctuation and an unbalanced `)`/`]` removed."""
    doi = raw
    while doi:
        if doi[-1] in ".,;:*_":
            doi = doi[:-1]
        elif doi[-1] == ")" and doi.count("(") < doi.count(")"):
            doi = doi[:-1]
        elif doi[-1] == "]" and doi.count("[") < doi.count("]"):
            doi = doi[:-1]
        else:
            break
    return doi.lower()


def _check_citation(card: Card, lines: list[Line], sec: Section | None) -> None:
    if sec is None:
        return
    raw = _raw_text(lines)
    card.dois = sorted({normalise_doi(m.group(0)) for m in _DOI_RE.finditer(raw)})
    if not card.dois and not _URL_RE.search(raw):
        card.add(ERROR, "citation-no-link",
                 "`## Citation` has neither a DOI (10.x/y) nor an http(s) URL", sec.line)
    years = [int(m.group(1)) for m in _YEAR_RE.finditer(raw)]
    if years:
        card.years = (min(years), max(years))
    else:
        card.add(WARNING, "citation-no-year",
                 "no `(YYYY)` publication year in `## Citation`", sec.line)


def _check_family(card: Card, lines: list[Line], sec: Section | None,
                  vocab: FamilyVocab) -> None:
    if sec is None:
        return
    spans, prose = _code_and_prose(lines)
    allowed = (*vocab.families, vocab.unmapped)
    if not spans:
        words = " ".join(t for _, t in prose).split()
        first = words[0].strip("*_.,;:") if words else ""
        hint = (f" -- write it in backticks: `{first}`" if first in allowed or first in
                vocab.aliases else "")
        card.add(ERROR, "family-missing",
                 f"`## hyp_lab family` has no backticked family token{hint}", sec.line)
        return
    token, line = spans[0].text, spans[0].line
    card.family_written = token
    if token in allowed:
        card.family = token
    elif token in vocab.aliases:
        card.family = vocab.aliases[token]
        card.add(WARNING, "family-alias",
                 f"`{token}` is an alias; the canonical family is `{card.family}`", line)
    else:
        card.add(ERROR, "family-unknown",
                 f"`{token}` is not in {FAMILIES_NAME} (backend/config.py) and is not "
                 f"`{vocab.unmapped}`{_close(token, allowed)}", line)


def _check_verdict(card: Card, lines: list[Line], sec: Section | None) -> None:
    if sec is None:
        return
    content = [ln for ln in lines if not ln.fenced and ln.text.strip()]
    if not content:
        card.add(ERROR, "verdict-missing", "`## Verdict` is empty", sec.line)
        return
    first = content[0]
    m = _VERDICT_DECL_RE.match(first.text)
    if not m:
        card.add(ERROR, "verdict-invalid",
                 f"the verdict line must START with one of {', '.join(VERDICTS)} written as "
                 f"WORD, WORD., **WORD** or **WORD.**; got {first.text.strip()[:70]!r}",
                 first.no)
        return
    card.verdict = m.group("bold") or m.group("plain")
    if _VERDICT_JOINED_RE.match(first.text[m.end():]):
        card.add(ERROR, "verdict-multiple",
                 "the verdict line declares more than one verdict -- pick exactly one",
                 first.no)
    _, prose = _code_and_prose(lines)
    also: set[str] = set()
    for no, txt in prose:
        if no != first.no and _VERDICT_ONLY_LINE_RE.match(txt):
            card.add(ERROR, "verdict-multiple",
                     f"a second verdict declaration ({txt.strip()}); the first line "
                     f"already declares {card.verdict}", no)
        also.update(w for w in _VERDICT_BOLD_RE.findall(txt) if w != card.verdict)
    card.verdict_also = [v for v in VERDICTS if v in also]


def _check_needs_evidence(card: Card, lines: list[Line], sec: Section | None) -> None:
    if sec is None:
        return
    entries = _bullets(lines)
    for no, txt in entries:
        if not txt.strip("`*_ "):
            card.add(ERROR, "needs-evidence-empty", "empty needs_evidence bullet", no)
    card.needs_evidence = [t for _, t in entries if t.strip("`*_ ")]
    n = len(card.needs_evidence)
    if not NEEDS_EVIDENCE_MIN <= n <= NEEDS_EVIDENCE_MAX:
        card.add(ERROR, "needs-evidence-count",
                 f"`## needs_evidence` has {n} non-empty bullet(s); it needs "
                 f"{NEEDS_EVIDENCE_MIN} to {NEEDS_EVIDENCE_MAX}", sec.line)


def _check_placeholders(card: Card, prose: list[tuple[int, str]],
                        dataset_lines: set[int]) -> None:
    for no, txt in sorted(prose):
        hits = [m.group(1) for m in _TBD_RE.finditer(txt)]
        for m in _ANGLE_RE.finditer(txt):
            inner = m.group(1)
            tag = _HTML_TAG_RE.match(inner)
            if tag and tag.group(1).lower() in _HTML_TAGS:
                continue                                   # <br>, <sup>, <a href=...>
            if _SCHEME_RE.match(inner) or ("@" in inner and " " not in inner):
                continue                                   # <https://...>, <a@b.c>
            hits.append(f"<{inner}>")
        for h in hits:
            if card.verdict == "NEEDS_DATA" and no in dataset_lines:
                card.add(WARNING, "placeholder",
                         f"placeholder {h!r} in the dataset section (allowed while the "
                         "verdict is NEEDS_DATA)", no)
            else:
                card.add(ERROR, "placeholder", f"unfilled placeholder {h!r}", no)


def _check_paths(card: Card, spans: list[Span], repo_root: Path) -> None:
    seen: set[tuple[str, int]] = set()
    for span in spans:
        for word in span.text.split():
            word = word.strip("\"'")
            if not word or (word, span.line) in seen:
                continue
            seen.add((word, span.line))
            problem = _path_problem(word)
            if problem:
                card.add(ERROR, "path-not-repo-relative",
                         f"`{word}` is {problem}; write a repo-relative path", span.line)
                continue
            rel = word.replace("\\", "/")
            if not rel.startswith(TRACKED_PREFIXES) or _PATTERN_CHARS & set(rel):
                continue
            rel = re.sub(r"#.*$", "", rel)
            rel = re.sub(r"(\.[A-Za-z][A-Za-z0-9]*)::?[^/]*$", r"\1", rel)
            if not (repo_root / rel).exists():
                card.add(WARNING, "path-missing",
                         f"`{rel}` does not exist in this checkout", span.line)


def _path_problem(word: str) -> str | None:
    """Why `word` is not a repo-relative path, or None (also None for non-paths)."""
    if _SCHEME_RE.match(word) and "://" in word:
        return None                                        # a URL
    if re.match(r"^(?:doi:)?10\.\d{4,9}/", word):
        return None                                        # a DOI
    if _DRIVE_RE.match(word) or word.startswith("\\\\"):
        return "a Windows drive/UNC path"
    if _HOME_RE.match(word):
        return "a home-relative (~) path"
    if "/" not in word and "\\" not in word:
        return None
    segments = [s for s in re.split(r"[\\/]", word)]
    if ".." in segments:
        return "a path with a `..` segment"
    if word.startswith("/") and len(word) > 1:
        first = segments[1] if len(segments) > 1 else ""
        if first in _POSIX_ROOTS or _EXT_RE.search(segments[-1] or ""):
            return "an absolute path"
    return None


# ----------------------------------------------------------------------------- all cards
def list_card_paths(cards_dir: Path) -> list[Path]:
    """Every `*.md` card, SORTED: the filesystem's listing order must never leak out."""
    names = [n for n in os.listdir(cards_dir) if n.endswith(".md") and not n.startswith(".")]
    return [Path(cards_dir) / n for n in sorted(names) if (Path(cards_dir) / n).is_file()]


def _mentions(card: Card, other: Card) -> bool:
    names = {other.path.stem, other.path.name} | ({other.slug} if other.slug else set())
    return any(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(n)}(?![A-Za-z0-9_-])", card.text)
               for n in names)


def check_cards(cards_dir: Path, vocab: FamilyVocab,
                repo_root: Path = REPO_ROOT) -> list[Card]:
    cards = [parse_card(p, vocab, repo_root) for p in list_card_paths(Path(cards_dir))]

    by_slug: dict[str, list[Card]] = {}
    for c in cards:
        if c.slug:
            by_slug.setdefault(c.slug, []).append(c)
    for slug, group in by_slug.items():
        if len(group) < 2:
            continue
        # the card whose FILENAME is the slug owns it; every other claimant is the duplicate
        owner = next((c for c in group if c.path.stem == slug), group[0])
        for c in group:
            if c is not owner:
                c.add(ERROR, "slug-duplicate",
                      f"slug `{slug}` already belongs to {owner.path.name}")

    by_norm: dict[str, list[Card]] = {}
    for c in cards:
        if c.slug:
            by_norm.setdefault(re.sub(r"[\s_-]+", " ", c.slug.casefold()).strip(), []).append(c)
    for group in by_norm.values():
        if len({c.slug for c in group}) < 2:
            continue
        for c in group[1:]:
            if c.slug == group[0].slug:
                continue
            c.add(ERROR, "title-duplicate",
                  f"title `{c.slug}` is a near-duplicate of `{group[0].slug}` "
                  f"({group[0].path.name}); merge the cards or rename one")

    ordered = sorted(cards, key=lambda c: c.sort_key)
    for i, later in enumerate(ordered):
        for earlier in ordered[:i]:
            shared = sorted(set(later.dois) & set(earlier.dois))
            if shared and not _mentions(later, earlier):
                later.add(ERROR, "doi-duplicate",
                          f"DOI {', '.join(shared)} is also cited by "
                          f"{earlier.path.name}; cross-reference that card "
                          f"(`{earlier.slug or earlier.path.stem}`) or merge the two")
    return cards


# ----------------------------------------------------------------------------- the index
def _cell(text: str | None) -> str:
    if text is None or not str(text).strip():
        return "?"
    return " ".join(str(text).split()).replace("|", "\\|")


def render_index(cards: list[Card], index_path: Path) -> str:
    """INDEX.md as text: sorted by slug, LF, no timestamp -- same cards, same bytes."""
    lines = [
        "# Research intake card index (GENERATED, do not edit)",
        "",
        f"Generated by `{REGENERATE_CMD}` from the card files linked below; edits here are "
        f"overwritten -- regenerate with that command (`--check-index` exits 1 when stale).",
        "",
        "| card | topic | mechanism class | dataset status | hyp_lab family | verdict "
        "| open evidence | source years |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    tally = {v: 0 for v in VERDICTS}
    for c in sorted(cards, key=lambda c: c.sort_key):
        try:
            rel = Path(os.path.relpath(c.path, Path(index_path).parent)).as_posix()
        except ValueError:                                 # another drive on Windows
            rel = c.path.name
        link = f"[{_cell(c.slug or c.path.stem)}]({urllib.parse.quote(rel)})"
        if c.errors:
            link += f" (INVALID: {len(c.errors)} error{'s' if len(c.errors) != 1 else ''})"
        verdict = c.verdict
        if verdict:
            tally[verdict] += 1
            if c.verdict_also:
                verdict += " (" + ", ".join(f"+{v}" for v in c.verdict_also) + ")"
        years = None
        if c.years:
            years = str(c.years[0]) if c.years[0] == c.years[1] else f"{c.years[0]}-{c.years[1]}"
        family = f"`{c.family}`" if c.family else None
        lines.append("| " + " | ".join([
            link, _cell(c.topic), _cell(", ".join(c.mechanism_class) or None),
            _cell(c.dataset_status), _cell(family), _cell(verdict),
            str(len(c.needs_evidence)), _cell(years)]) + " |")
    lines += [
        "",
        f"{len(cards)} card{'s' if len(cards) != 1 else ''}; declared verdicts: "
        + ", ".join(f"{v} {n}" for v, n in tally.items())
        + ". `(+WORD)` marks a split verdict: the card's justification also gives WORD to a "
          "sub-construction. `open evidence` counts the card's `needs_evidence` questions.",
    ]
    return "\n".join(lines) + "\n"


def _read_normalised(path: Path) -> str | None:
    try:
        return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def index_state(cards: list[Card], index_path: Path) -> tuple[str, str]:
    """('current' | 'stale' | 'missing', a short diff when stale)."""
    if not Path(index_path).is_file():
        return "missing", ""
    want = render_index(cards, index_path)
    have = _read_normalised(Path(index_path))
    if have == want:
        return "current", ""
    diff = difflib.unified_diff((have or "").splitlines(), want.splitlines(),
                                "INDEX.md (on disk)", "INDEX.md (from the cards)", lineterm="", n=0)
    return "stale", "\n".join(list(diff)[:24])


def atomic_write_text(path: Path, text: str) -> None:
    """tmp + fsync + `os.replace`, bytes as given (LF stays LF on Windows too)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_index(cards: list[Card], index_path: Path) -> str:
    """Write INDEX.md unless it is already current. Returns 'written' or 'unchanged'."""
    want = render_index(cards, index_path)
    if _read_normalised(Path(index_path)) == want:
        return "unchanged"
    atomic_write_text(Path(index_path), want)
    return "written"


# ----------------------------------------------------------------------------- reporting
def summarise(cards: list[Card]) -> dict:
    return {"cards_checked": len(cards),
            "valid": sum(1 for c in cards if not c.errors),
            "warnings": sum(len(c.warnings) for c in cards),
            "errors": sum(len(c.errors) for c in cards)}


def summary_line(s: dict) -> str:
    return (f"cards checked: {s['cards_checked']}  valid: {s['valid']}  "
            f"warnings: {s['warnings']}  errors: {s['errors']}")


def _display(path: Path, repo_root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(path)


def _ordered_findings(card: Card) -> list[Finding]:
    return sorted(card.findings, key=lambda f: (f.level != ERROR, f.line or 0, f.code))


def card_record(card: Card, repo_root: Path) -> dict:
    return {
        "file": _display(card.path, repo_root), "slug": card.slug, "topic": card.topic,
        "mechanism_class": card.mechanism_class, "dataset_status": card.dataset_status,
        "hyp_lab_family": card.family, "hyp_lab_family_written": card.family_written,
        "verdict": card.verdict, "verdict_also": card.verdict_also,
        "needs_evidence": card.needs_evidence, "open_evidence": len(card.needs_evidence),
        "source_years": list(card.years) if card.years else None, "dois": card.dois,
        "errors": [f.as_dict() for f in _ordered_findings(card) if f.level == ERROR],
        "warnings": [f.as_dict() for f in _ordered_findings(card) if f.level == WARNING],
    }


def format_report(cards: list[Card], header: str, index_note: str | None) -> str:
    out = [header]
    for c in sorted(cards, key=lambda c: c.path.name):
        ne, nw = len(c.errors), len(c.warnings)
        status = "FAIL" if ne else ("WARN" if nw else "OK")
        counts = f"  ({ne} error(s), {nw} warning(s))" if (ne or nw) else ""
        out.append(f"  {status:<4}  {c.path.name}{counts}")
        for f in _ordered_findings(c):
            loc = f"L{f.line}" if f.line else "-"
            out.append(f"        {f.level.upper():<7} {loc:<5} {f.code}: {f.message}")
    if index_note:
        out.append(index_note)
    out.append(summary_line(summarise(cards)))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="research_intake_check",
        description="Validate docs/research_intake/cards/*.md and generate/check INDEX.md.")
    ap.add_argument("--cards-dir", type=Path, default=DEFAULT_CARDS_DIR)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                    help="the config.py whose HYP_LAB_FAMILIES is parsed (never imported)")
    ap.add_argument("--index", type=Path, default=None,
                    help=f"default: <cards-dir>/../{INDEX_FILENAME}")
    ap.add_argument("--repo-root", type=Path, default=REPO_ROOT,
                    help="root that tracked-looking paths are resolved against")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write-index", action="store_true",
                      help="write INDEX.md (atomic, deterministic; written even when cards "
                           "carry errors, which are marked INVALID and still exit 1)")
    mode.add_argument("--check-index", action="store_true",
                      help="exit 1 when INDEX.md is missing or differs from the cards")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

    cards_dir: Path = a.cards_dir
    if not cards_dir.is_dir():
        print(f"REFUSED: cards dir {cards_dir} does not exist -- nothing was checked",
              file=sys.stderr)
        return 2
    try:
        vocab = load_family_vocab(a.config)
    except VocabError as e:
        print(f"REFUSED: {e} -- nothing was checked", file=sys.stderr)
        return 2

    cards = check_cards(cards_dir, vocab, repo_root=a.repo_root)
    summary = summarise(cards)
    rc = 0 if summary["errors"] == 0 else 1
    index_path: Path = a.index or cards_dir.parent / INDEX_FILENAME
    index_shown = _display(index_path, a.repo_root)
    index_status, index_note, stale_diff = None, None, ""
    if a.write_index:
        index_status = write_index(cards, index_path)
        index_note = f"index: {index_shown} {index_status} ({len(cards)} row(s))"
    elif a.check_index:
        index_status, stale_diff = index_state(cards, index_path)
        if index_status != "current":
            rc = 1
        index_note = (f"index: {index_shown} is CURRENT" if index_status == "current" else
                      f"index: {index_shown} is {index_status.upper()} -- run `{REGENERATE_CMD}`")

    if a.json:
        payload = {
            "cards_dir": _display(cards_dir, a.repo_root),
            "config": _display(a.config, a.repo_root),
            "summary": summary,
            "index": {"path": index_shown, "status": index_status or "not_checked"},
            "cards": [card_record(c, a.repo_root) for c in sorted(cards, key=lambda c: c.sort_key)],
        }
        print(json.dumps(payload, indent=2))
    else:
        header = (f"research intake check: {_display(cards_dir, a.repo_root)} "
                  f"({len(cards)} card(s); {len(vocab.families)} hyp_lab families, "
                  f"{len(vocab.aliases)} alias(es) from {_display(a.config, a.repo_root)})")
        print(format_report(cards, header, index_note))
        if stale_diff:
            print(stale_diff)
    return rc


if __name__ == "__main__":
    # A redirected stdout on Windows is cp1252; a card quoting a non-Latin character must not
    # turn a report into a UnicodeEncodeError. (JSON output is ASCII-escaped regardless.)
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
