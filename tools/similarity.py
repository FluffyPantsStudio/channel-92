"""Compare two source trees for copied code, prose and naming.

    python tools/similarity.py OLD_DIR NEW_DIR [--json REPORT] [--allow FILE]

Four checks, each with its pass rule (see docs/clean-room.md):

  names  identifiers defined in Python (functions, classes, arguments, variables,
         attributes assigned), compared case- and underscore-blind, after a stoplist
         of keywords, builtins, standard-library names, numpy names and a few
         conventional names. The measure counts DISTINCTIVE names only: six letters
         or more, or an underscore inside (a leading or trailing underscore is a
         privacy mark and does not count), and not in STANDARD_WORDS. PASS when
         under 5 % of the new tree's distinctive identifiers also occur in the old
         tree. The strict number (every name after the stoplist) is printed too.
  prose  docstrings, comments, string literals of five or more words, and Markdown
         or text files, as normalised sentences and 6-word runs. Standard technical
         phrases (STANDARD_PHRASES: WCAG terms, ffmpeg option names, loudness units)
         are cut out first and no run crosses one. PASS when no sentence of five or
         more words and no 6-word run is shared.
  code   Python lines without comments, docstrings, imports, blanks and bracket-only
         lines; windows of 8 lines compared as written (literal) and with names as
         ID and literals as LIT (shape). PASS when no literal run exists, shape runs
         cover under 1 % of the new code lines, and no shape run is over 12 lines.
  keys   JSON key names (from .json files and string keys in Python) plus CLI verbs
         and flags. The measure counts distinctive keys (six letters or more, or an
         underscore or hyphen inside) outside STANDARD_KEYS (ffprobe fields, HTTP
         headers, ComfyUI API fields, common flags). PASS when under 5 % of those
         also occur in the old set; the strict number is printed too.

No allow-list is read by default: every shared name and key counts. --allow FILE
exempts the names in FILE (one per line with its reason) for a one-off look; every
allowed name is printed, and a release check is run without it.

docs/shared-vocabulary.md lists every stop-list entry and why it is standard.

Positions are printed for the new tree only. Exit code: 0 pass, 1 fail, 2 usage.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import importlib
import io
import json
import keyword
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

WINDOW = 8
MIN_DISTINCT_IN_WINDOW = 4
MAX_SHAPE_SHARE = 0.01
MAX_SHAPE_RUN = 12
MAX_NAME_SHARE = 0.05
MAX_KEY_SHARE = 0.05
MIN_SENTENCE_WORDS = 5
SHINGLE_WORDS = 6
MIN_CONTENT_WORDS_IN_SHINGLE = 3
MIN_LITERAL_PROSE_WORDS = 5

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "build", "dist"}
PROSE_SUFFIXES = {".md", ".txt", ".rst"}

CONVENTIONAL_NAMES = {
    "self", "cls", "args", "kwargs", "argv", "parser", "subparsers", "main", "path", "paths", "data",
    "out", "result", "results", "value", "values", "key", "keys", "name", "names", "line", "lines",
    "text", "item", "items", "err", "exc", "fh", "src", "dst", "root", "tmp", "idx", "index", "total",
    "config", "options", "opts", "start", "end", "size", "count", "parts", "row", "rows", "msg",
}
DOMAIN_NAMES = {"bpm", "fps", "lufs", "rate", "sr", "wav", "hz", "db", "dbfs", "rms", "stem", "stems", "beats"}
GENERIC_KEYS = {"name", "type", "id", "path", "version", "data", "items", "value", "key", "description",
                "help", "verbose", "quiet", "out", "output", "json", "--help", "--version", "--verbose",
                "--quiet", "--out", "--output", "--json"}
STOP_WORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "it", "this", "that",
    "with", "as", "at", "by", "from", "if", "not", "no", "each", "every", "one", "all", "its", "we", "our",
    "you", "your", "was", "were", "has", "have", "so", "but", "when", "then", "than", "there", "into", "can",
    "will", "do", "does", "any", "only", "out", "up", "else", "which", "what", "who", "how", "per",
}
STDLIB_MODULES_TO_EXPAND = (
    "os", "os.path", "sys", "json", "re", "math", "pathlib", "argparse", "hashlib", "shutil", "subprocess",
    "itertools", "functools", "collections", "typing", "dataclasses", "struct", "time", "datetime",
    "random", "statistics", "io", "tempfile", "logging", "string", "textwrap", "threading", "queue",
    "urllib.request", "http.server", "socket", "glob", "fnmatch", "copy", "enum", "abc", "wave", "csv",
)
LIBRARY_MODULES_TO_EXPAND = ("numpy",)

BRACKET_ONLY = set("()[]{},:;")

DISTINCTIVE_MIN_LENGTH = 6
REPORT_LIMIT = 200

# Words any audio, video, film, music or HTTP program uses for the same thing. Documented one by one in
# docs/shared-vocabulary.md; a name here leaves the distinctive measure, never the strict number.
STANDARD_WORDS = {
    # audio
    "channels", "samples", "sample_rate", "stereo", "loudness", "envelope", "spectrum", "onsets", "decibels",
    # video
    "frames", "pixels", "duration", "bitrate", "height", "codec",
    # film
    "camera", "framing", "cutaway",
    # music
    "downbeat", "chorus", "lyrics", "tempo",
    # HTTP
    "content", "headers", "status", "timeout", "request", "response",
    # Blender's Python API (bpy, bmesh): attributes a Blender script has to set by these names
    "clip_end", "engine", "material", "smooth",
    # English function words of six letters or more: they name a position or a condition, not a design
    "before", "behind", "during", "within", "without", "inside", "around", "toward", "towards", "through",
    "between", "beyond", "across", "against", "unless", "whether", "already", "always", "enough", "rather",
}
# JSON keys and command-line flags fixed by a tool, a format or a convention outside this project.
STANDARD_KEYS = {
    # ffprobe's output fields
    "avg_frame_rate", "r_frame_rate", "nb_frames", "duration", "format", "streams", "width", "height", "codec_name",
    "pix_fmt",
    # HTTP headers
    "Content-Type", "Content-Length",
    # ComfyUI's HTTP API
    "prompt", "client_id", "prompt_id", "class_type", "inputs", "outputs", "images", "filename", "subfolder",
    "status_str", "completed", "messages", "exec_info", "queue_running", "queue_pending", "system_stats", "devices",
    "vram_total", "vram_free", "status",
    # Blender's Python API: the key of the Cycles add-on in bpy.context.preferences.addons
    "cycles",
    # units and media fields with one meaning everywhere
    "fps", "frames", "seconds", "channels", "sample_rate", "bpm", "lufs",
    # flags with one meaning in every command-line tool
    "--dry-run", "--timeout", "--force", "--host", "--port", "--seed", "--fps", "--width", "--height", "--limit",
}
# Phrases fixed by a standard or a tool. Cut out of prose before sentences and 6-word runs are formed.
STANDARD_PHRASES = (
    "WCAG 2.3.1's", "WCAG 2.3.1", "general flash threshold", "red flash threshold", "red flash rule",
    "relative luminance", "linearised sRGB", "linearized sRGB",
    "force_original_aspect_ratio=increase", "force_original_aspect_ratio=decrease",
    "bicubic+accurate_rnd+full_chroma_int+bitexact", "setpts=PTS-STARTPTS", "-fps_mode passthrough",
    "integrated loudness", "true peak", "sample peak", "loudness range", "LUFS", "dBFS", "dBTP", "LU",
)


def _norm_ident(name: str) -> str:
    return name.replace("_", "").lower()


def _distinctive_name(name: str) -> bool:
    """Six letters or more, or an underscore inside; leading and trailing underscores do not count."""
    core = name.strip("_")
    return len(core) >= DISTINCTIVE_MIN_LENGTH or "_" in core


def _distinctive_key(key: str) -> bool:
    core = key.lstrip("-")
    return len(core) >= DISTINCTIVE_MIN_LENGTH or "_" in core or "-" in core


def _build_stoplist() -> set[str]:
    words = set(keyword.kwlist) | set(getattr(keyword, "softkwlist", [])) | set(dir(builtins))
    words |= set(getattr(sys, "stdlib_module_names", ()))
    for module_name in STDLIB_MODULES_TO_EXPAND + LIBRARY_MODULES_TO_EXPAND:
        try:
            words |= set(dir(importlib.import_module(module_name)))
        except ImportError:
            continue
    words |= CONVENTIONAL_NAMES | DOMAIN_NAMES
    return {_norm_ident(w) for w in words}


STOPLIST = _build_stoplist()
STANDARD_NORM = {_norm_ident(w) for w in STANDARD_WORDS}
STANDARD_KEYS_LOWER = {k.lower() for k in STANDARD_KEYS}


# ---- scanning ------------------------------------------------------------------


@dataclass
class Scan:
    """What one tree contains, keyed by normalised form, valued by first position."""

    idents: dict = field(default_factory=dict)      # norm -> (shown name, "file:line")
    sentences: dict = field(default_factory=dict)   # sentence -> "file:line"
    shingles: dict = field(default_factory=dict)    # 6-word run -> "file:line"
    keys: dict = field(default_factory=dict)        # key -> "file:line"
    verbs: dict = field(default_factory=dict)       # verb or flag -> "file:line"
    code: dict = field(default_factory=dict)        # rel file -> [(lineno, literal, shape)]
    skipped: list = field(default_factory=list)


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


def _import_lines(tree: ast.AST) -> set[int]:
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            lines.update(range(node.lineno, node.end_lineno + 1))
    return lines


def _is_string_part(tok: tokenize.TokenInfo) -> str | None:
    kind = tokenize.tok_name.get(tok.type, "")
    if kind.endswith("STRING_START"):
        return "start"
    if kind.endswith("STRING_END"):
        return "end"
    return None


def code_lines(source: str) -> list[tuple[int, str, str]]:
    """Return (line number, literal form, shape form) for each line of real code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    dropped = _docstring_lines(tree) | _import_lines(tree)
    per_line: dict[int, list[tuple[str, str]]] = {}
    depth = 0
    fstring_line = None
    fstring_text: list[str] = []
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
            tokenize.ENCODING, tokenize.ENDMARKER}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        part = _is_string_part(tok)
        if part == "start":
            depth += 1
            if depth == 1:
                fstring_line, fstring_text = tok.start[0], []
        if depth:
            fstring_text.append(tok.string)
            if part == "end":
                depth -= 1
                if depth == 0:
                    per_line.setdefault(fstring_line, []).append(("".join(fstring_text), "LIT"))
            continue
        if tok.type in skip:
            continue
        if tok.type == tokenize.NAME:
            shape = tok.string if keyword.iskeyword(tok.string) else "ID"
        elif tok.type in (tokenize.NUMBER, tokenize.STRING):
            shape = "LIT"
        else:
            shape = tok.string
        per_line.setdefault(tok.start[0], []).append((tok.string, shape))
    result = []
    for lineno in sorted(per_line):
        if lineno in dropped:
            continue
        toks = per_line[lineno]
        if all(text in BRACKET_ONLY for text, _ in toks):
            continue
        literal = " ".join(text for text, _ in toks)
        shape_parts: list[str] = []
        for _, shape in toks:
            if shape == "LIT" and shape_parts and shape_parts[-1] == "LIT":
                continue  # adjacent literals (implicit concatenation) are one
            shape_parts.append(shape)
        result.append((lineno, _tidy(literal), " ".join(shape_parts)))
    return result


def _tidy(literal: str) -> str:
    return re.sub(r"\s+", " ", literal).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[.!?]+(?:\s|$)|\n\s*\n|\n\s*[-*#>|]+\s", text) if s.strip()]


STANDARD_PHRASE_WORDS = sorted({tuple(_words(p)) for p in STANDARD_PHRASES}, key=len, reverse=True)


def standard_free_segments(words: list[str]) -> list[list[str]]:
    """The word list with every standard phrase cut out: the pieces between the cuts, in order."""
    segments: list[list[str]] = [[]]
    i = 0
    while i < len(words):
        hit = next((len(p) for p in STANDARD_PHRASE_WORDS if tuple(words[i:i + len(p)]) == p), 0)
        if hit:
            segments.append([])
            i += hit
        else:
            segments[-1].append(words[i])
            i += 1
    return [segment for segment in segments if segment]


def _add_prose(scan: Scan, text: str, where: str) -> None:
    for sentence in _split_sentences(text):
        words = [w for segment in standard_free_segments(_words(sentence)) for w in segment]
        if len(words) >= MIN_SENTENCE_WORDS:
            scan.sentences.setdefault(" ".join(words), where)
    for words in standard_free_segments(_words(text)):
        for i in range(len(words) - SHINGLE_WORDS + 1):
            run = words[i:i + SHINGLE_WORDS]
            if sum(w not in STOP_WORDS for w in run) >= MIN_CONTENT_WORDS_IN_SHINGLE:
                scan.shingles.setdefault(" ".join(run), where)


def _comment_blocks(source: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    last_line = None
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type != tokenize.COMMENT:
                continue
            text = tok.string.lstrip("#").strip()
            if blocks and last_line == tok.start[0] - 1:
                blocks[-1] = (blocks[-1][0], blocks[-1][1] + " " + text)
            else:
                blocks.append((tok.start[0], text))
            last_line = tok.start[0]
    except (tokenize.TokenError, SyntaxError):
        pass
    return blocks


class _PyVisitor(ast.NodeVisitor):
    def __init__(self, scan: Scan, rel: str):
        self.scan, self.rel = scan, rel

    def _ident(self, name: str, lineno: int) -> None:
        if name.startswith("__") and name.endswith("__"):
            return  # protocol names (__init__, __call__) belong to the language
        norm = _norm_ident(name)
        if len(norm) > 1:
            self.scan.idents.setdefault(norm, (name, f"{self.rel}:{lineno}"))

    def _key(self, node: ast.AST, store: dict) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
            store.setdefault(node.value, f"{self.rel}:{node.lineno}")

    def visit_FunctionDef(self, node):
        self._ident(node.name, node.lineno)
        all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        all_args += [a for a in (node.args.vararg, node.args.kwarg) if a]
        for arg in all_args:
            self._ident(arg.arg, arg.lineno)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._ident(node.name, node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self._ident(node.id, node.lineno)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Store):
            self._ident(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_Dict(self, node):
        for key in node.keys:
            if key is not None:
                self._key(key, self.scan.keys)
        self.generic_visit(node)

    def visit_Subscript(self, node):
        self._key(node.slice, self.scan.keys)
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute) and node.args:
            if func.attr == "get":
                self._key(node.args[0], self.scan.keys)
            elif func.attr == "add_parser":
                self._key(node.args[0], self.scan.verbs)
            elif func.attr == "add_argument":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--"):
                        self._key(arg, self.scan.verbs)
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and len(_words(node.value)) >= MIN_LITERAL_PROSE_WORDS:
            _add_prose(self.scan, node.value, f"{self.rel}:{node.lineno}")


def _scan_python(scan: Scan, rel: str, source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        scan.skipped.append(rel)
        return
    _PyVisitor(scan, rel).visit(tree)  # docstrings arrive here as string constants
    for lineno, text in _comment_blocks(source):
        _add_prose(scan, text, f"{rel}:{lineno}")
    scan.code[rel] = code_lines(source)


def _json_keys(obj, store: dict, where: str) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            store.setdefault(key, where)
            _json_keys(value, store, where)
    elif isinstance(obj, list):
        for value in obj:
            _json_keys(value, store, where)


def _scan_prose_file(scan: Scan, rel: str, text: str) -> None:
    lineno = 1
    for para in re.split(r"(\n\s*\n)", text):
        if para.strip():
            _add_prose(scan, para, f"{rel}:{lineno}")
        lineno += para.count("\n")


def scan_tree(root) -> Scan:
    root = Path(root)
    scan = Scan()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix not in {".py", ".json"} | PROSE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            scan.skipped.append(rel)
            continue
        if suffix == ".py":
            _scan_python(scan, rel, text)
        elif suffix == ".json":
            try:
                _json_keys(json.loads(text), scan.keys, f"{rel}:1")
            except json.JSONDecodeError:
                scan.skipped.append(rel)
        else:
            _scan_prose_file(scan, rel, text)
    return scan


# ---- comparing -----------------------------------------------------------------


def _windows(lines: list[tuple[int, str, str]], form: int) -> dict:
    found = {}
    for i in range(len(lines) - WINDOW + 1):
        chunk = tuple(line[form] for line in lines[i:i + WINDOW])
        if len(set(chunk)) >= MIN_DISTINCT_IN_WINDOW:
            found.setdefault(chunk, i)
    return found


def _runs(old: Scan, new: Scan, form: int) -> list[dict]:
    old_hashes = set()
    for lines in old.code.values():
        old_hashes.update(_windows(lines, form))
    runs = []
    for rel, lines in sorted(new.code.items()):
        hits = [i for i in range(len(lines) - WINDOW + 1)
                if tuple(line[form] for line in lines[i:i + WINDOW]) in old_hashes]
        start = prev = None
        for i in hits + [None]:
            if start is not None and (i is None or i != prev + 1):
                last = prev + WINDOW - 1
                runs.append({"where": f"{rel}:{lines[start][0]}-{lines[last][0]}", "length": last - start + 1})
                start = None
            if i is not None and start is None:
                start = i
            prev = i
    return runs


def read_allow(path) -> dict:
    """Read 'name  # reason' lines; blank lines and lines starting with # are skipped."""
    allowed = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition("#")
        allowed[name.strip()] = reason.strip()
    return allowed


def _share(new_set: set, shared: set) -> float:
    return len(shared) / len(new_set) if new_set else 0.0


def compare(old_root, new_root, allow: dict | None = None) -> dict:
    allow = allow or {}
    allowed_norm = {_norm_ident(name) for name in allow}
    old, new = scan_tree(old_root), scan_tree(new_root)

    strict_idents = {n for n in new.idents if n not in STOPLIST and n not in allowed_norm}
    old_idents = {n for n in old.idents if n not in STOPLIST}
    strict_shared_idents = strict_idents & old_idents
    new_idents = {n for n in strict_idents if n not in STANDARD_NORM and _distinctive_name(new.idents[n][0])}
    shared_idents = sorted(new_idents & old_idents)
    name_share = _share(new_idents, set(shared_idents))

    new_keys = {**{k: v for k, v in new.keys.items()}, **{k: v for k, v in new.verbs.items()}}
    old_keys = set(old.keys) | set(old.verbs)
    strict_keys = {k for k in new_keys if k not in GENERIC_KEYS and k not in allow}
    strict_shared_keys = strict_keys & old_keys
    candidate_keys = {k for k in strict_keys if k.lower() not in STANDARD_KEYS_LOWER and _distinctive_key(k)}
    shared_keys = sorted(candidate_keys & old_keys)
    key_share = _share(candidate_keys, set(shared_keys))

    shared_sentences = sorted(set(new.sentences) & set(old.sentences))
    shared_shingles = sorted(set(new.shingles) & set(old.shingles))

    literal_runs = _runs(old, new, 1)
    shape_runs = _runs(old, new, 2)
    new_code_lines = sum(len(lines) for lines in new.code.values())
    shape_covered = sum(run["length"] for run in shape_runs)
    shape_share = shape_covered / new_code_lines if new_code_lines else 0.0
    longest_shape = max((run["length"] for run in shape_runs), default=0)

    checks = {
        "names": name_share < MAX_NAME_SHARE,
        "prose": not shared_sentences and not shared_shingles,
        "code": not literal_runs and shape_share < MAX_SHAPE_SHARE and longest_shape <= MAX_SHAPE_RUN,
        "keys": key_share < MAX_KEY_SHARE,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "thresholds": {
            "name_share_below": MAX_NAME_SHARE, "key_share_below": MAX_KEY_SHARE,
            "window_lines": WINDOW, "shape_share_below": MAX_SHAPE_SHARE, "shape_run_at_most": MAX_SHAPE_RUN,
            "sentence_min_words": MIN_SENTENCE_WORDS, "shingle_words": SHINGLE_WORDS,
        },
        "names": {
            "new_count": len(new_idents), "share": name_share,
            "shared": [{"name": new.idents[n][0], "where": new.idents[n][1]} for n in shared_idents],
            "strict_count": len(strict_idents), "strict_shared": len(strict_shared_idents),
            "strict_share": _share(strict_idents, strict_shared_idents),
            "strict_list": sorted(new.idents[n][0] for n in strict_shared_idents),
        },
        "keys": {
            "new_count": len(candidate_keys), "share": key_share,
            "shared": [{"name": k, "where": new_keys[k]} for k in shared_keys],
            "strict_count": len(strict_keys), "strict_shared": len(strict_shared_keys),
            "strict_share": _share(strict_keys, strict_shared_keys),
            "strict_list": sorted(strict_shared_keys),
        },
        "prose": {
            "sentences": [{"text": s, "where": new.sentences[s]} for s in shared_sentences],
            "shingles": [{"text": s, "where": new.shingles[s]} for s in shared_shingles],
        },
        "code": {
            "new_lines": new_code_lines, "literal_runs": literal_runs, "shape_runs": shape_runs,
            "shape_share": shape_share, "longest_shape_run": longest_shape,
        },
        "allowed": [{"name": name, "reason": reason} for name, reason in sorted(allow.items())],
        "skipped_new": new.skipped,
    }


# ---- report --------------------------------------------------------------------


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _where_key(where: str):
    rel, _, line = where.rpartition(":")
    return rel, int(line) if line.isdigit() else 0


def _prose_lines(prose: dict) -> list[str]:
    """One line per new-side position: counts of shared sentences and runs, first words shown."""
    by_where: dict[str, list] = {}
    for kind in ("sentences", "shingles"):
        for item in prose[kind]:
            entry = by_where.setdefault(item["where"], [0, 0, item["text"]])
            entry[0 if kind == "sentences" else 1] += 1
            if kind == "sentences":
                entry[2] = item["text"]
    lines = []
    for where in sorted(by_where, key=_where_key):
        n_sent, n_runs, text = by_where[where]
        snippet = " ".join(text.split()[:8])
        lines.append(f"    {where}  sentences {n_sent}, runs {n_runs}  \"{snippet} ...\"")
    return lines


def format_report(report: dict, old_root, new_root, limit: int = REPORT_LIMIT) -> str:
    out = [f"similarity: old={old_root} new={new_root}"]
    names, keys, prose, code, checks = (report[k] for k in ("names", "keys", "prose", "code", "checks"))
    out.append(f"[names] distinctive: {len(names['shared'])} of {names['new_count']} new identifiers also in old "
               f"({names['share']:.1%}, limit {MAX_NAME_SHARE:.0%})  {_verdict(checks['names'])}")
    out.append(f"    strict (every name after the stop-list): {names['strict_shared']} of {names['strict_count']} "
               f"({names['strict_share']:.1%}); distinctive = {DISTINCTIVE_MIN_LENGTH}+ letters or an inner "
               "underscore, outside STANDARD_WORDS")
    out += [f"    {item['name']}  {item['where']}" for item in names["shared"][:limit]]
    out.append(f"[prose] shared sentences {len(prose['sentences'])}, shared {SHINGLE_WORDS}-word runs "
               f"{len(prose['shingles'])} (limit 0)  {_verdict(checks['prose'])}")
    out += _prose_lines(prose)[:limit]
    out.append(f"[code] literal runs {len(code['literal_runs'])} (limit 0); shape runs {len(code['shape_runs'])} "
               f"covering {code['shape_share']:.1%} of {code['new_lines']} lines, longest {code['longest_shape_run']} "
               f"(limits {MAX_SHAPE_SHARE:.0%}, {MAX_SHAPE_RUN})  {_verdict(checks['code'])}")
    out += [f"    literal  {run['where']}  ({run['length']} lines)" for run in code["literal_runs"][:limit]]
    out += [f"    shape    {run['where']}  ({run['length']} lines)" for run in code["shape_runs"][:limit]]
    out.append(f"[keys] distinctive: {len(keys['shared'])} of {keys['new_count']} new JSON keys and CLI verbs also "
               f"in old ({keys['share']:.1%}, limit {MAX_KEY_SHARE:.0%})  {_verdict(checks['keys'])}")
    out.append(f"    strict (every key after the generic list): {keys['strict_shared']} of {keys['strict_count']} "
               f"({keys['strict_share']:.1%}); distinctive = {DISTINCTIVE_MIN_LENGTH}+ letters or an inner "
               "underscore or hyphen, outside STANDARD_KEYS")
    out += [f"    {item['name']}  {item['where']}" for item in keys["shared"][:limit]]
    if report["allowed"]:
        out.append("[allowed] " + ", ".join(f"{a['name']} ({a['reason'] or 'no reason given'})"
                                            for a in report["allowed"]))
    if report["skipped_new"]:
        out.append("[skipped in new] " + ", ".join(report["skipped_new"]))
    out.append(f"RESULT: {_verdict(report['pass'])}")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare an old and a new source tree for copying.")
    parser.add_argument("old_dir")
    parser.add_argument("new_dir")
    parser.add_argument("--allow", help="file of 'name  # reason' lines exempt from the name and key checks "
                                        "(none by default; a release check never passes one)")
    parser.add_argument("--json", help="also write the full report as JSON here")
    args = parser.parse_args(argv)
    for folder in (args.old_dir, args.new_dir):
        if not Path(folder).is_dir():
            print(f"error: not a folder: {folder}", file=sys.stderr)
            return 2
    try:
        allow = read_allow(args.allow) if args.allow else {}
    except OSError as err:
        print(f"error: cannot read allow file: {err}", file=sys.stderr)
        return 2
    report = compare(args.old_dir, args.new_dir, allow)
    print(format_report(report, args.old_dir, args.new_dir))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
