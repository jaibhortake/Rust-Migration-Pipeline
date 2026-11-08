"""A project is a set of source files in one language. Loads pasted code, uploaded files or a zip, safely."""

import io
import posixpath
import zipfile
from dataclasses import dataclass, field

from app.config import settings

EXTS = {"python": (".py",), "cpp": (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h", ".hxx")}
CPP_SOURCES = (".cpp", ".cc", ".cxx")
CPP_HEADERS = (".hpp", ".hh", ".h", ".hxx")
SKIP_DIRS = {"__pycache__", ".git", "build", "venv", ".venv", "node_modules", "target", "cmake-build-debug"}


class ProjectError(ValueError):
    pass


@dataclass
class Project:
    language: str
    files: dict[str, str] = field(default_factory=dict)  # posix relative path -> text

    @property
    def loc(self) -> int:
        return sum(len([ln for ln in t.splitlines() if ln.strip()]) for t in self.files.values())


def clean_path(raw: str) -> str:
    """Normalise to a safe relative posix path; reject traversal and absolute paths."""
    p = raw.replace("\\", "/").strip()
    if not p or p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        raise ProjectError(f"invalid path: {raw!r}")
    norm = posixpath.normpath(p)
    if norm.startswith("..") or norm == "." or "/../" in f"/{norm}/":
        raise ProjectError(f"invalid path: {raw!r}")
    return norm


def language_of(path: str) -> str | None:
    for lang, exts in EXTS.items():
        if path.lower().endswith(exts):
            return lang
    return None


def build_project(files: dict[str, str], language: str | None = None) -> Project:
    if not files:
        raise ProjectError("no source files")
    cleaned: dict[str, str] = {}
    langs = set()
    for raw, text in files.items():
        path = clean_path(raw)
        lang = language_of(path)
        if lang is None:
            continue  # ignore READMEs, build files, ...
        if len(text) > settings.max_file_chars:
            raise ProjectError(f"{path} is larger than {settings.max_file_chars} characters")
        langs.add(lang)
        cleaned[path] = text.replace("\r\n", "\n")
    if not cleaned:
        raise ProjectError("no C++ or Python source files found")
    if len(langs) > 1:
        raise ProjectError("mixed C++ and Python files: migrate one language per project")
    lang = langs.pop()
    if language and language != lang:
        raise ProjectError(f"files are {lang}, not {language}")
    if len(cleaned) > settings.max_files:
        raise ProjectError(f"too many files ({len(cleaned)} > {settings.max_files})")
    if sum(len(t) for t in cleaned.values()) > settings.max_upload_bytes:
        raise ProjectError("project is too large")
    return Project(lang, dict(sorted(cleaned.items())))


def files_from_zip(data: bytes) -> dict[str, str]:
    if len(data) > settings.max_upload_bytes:
        raise ProjectError("zip is too large")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ProjectError("not a valid zip file") from e
    out: dict[str, str] = {}
    total = 0
    for info in zf.infolist():
        if info.is_dir() or language_of(info.filename) is None:
            continue
        parts = info.filename.replace("\\", "/").split("/")
        if any(p in SKIP_DIRS for p in parts):
            continue
        total += info.file_size  # declared size: guards against zip bombs before reading
        if total > settings.max_upload_bytes * 4 or info.file_size > settings.max_file_chars * 4:
            raise ProjectError("zip contents are too large")
        out[clean_path(info.filename)] = zf.read(info).decode("utf-8", errors="replace")
    return _strip_common_root(out)


def _strip_common_root(files: dict[str, str]) -> dict[str, str]:
    """`myproj/src/a.py` and `myproj/b.py` -> `src/a.py`, `b.py`."""
    if not files:
        return files
    first = [p.split("/") for p in files]
    while all(len(p) > 1 for p in first) and len({p[0] for p in first}) == 1:
        first = [p[1:] for p in first]
    return {"/".join(p): t for p, t in zip(first, files.values(), strict=True)}
