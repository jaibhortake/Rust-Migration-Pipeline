"""Build manifests that describe a project beyond its source files: requirements.txt and CMakeLists.txt."""

import posixpath
import re

MANIFEST_NAMES = {"requirements.txt": "requirements", "cmakelists.txt": "cmake"}

# PyPI package -> import name where they differ
PY_IMPORT_NAME = {
    "pyyaml": "yaml",
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "python-dateutil": "dateutil",
    "attrs": "attr",
}


def manifest_kind(path: str) -> str | None:
    return MANIFEST_NAMES.get(posixpath.basename(path).lower())


def parse_requirements(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        name = re.split(r"[<>=!~;\[ @]", line, maxsplit=1)[0].strip()
        if name and name.lower() not in names:
            names.append(name.lower())
    return names


def import_name(package: str) -> str:
    return PY_IMPORT_NAME.get(package, package.replace("-", "_"))


_CMD = re.compile(r"(?is)\b([a-z_]+)\s*\(([^()]*)\)")


def _args(body: str) -> list[str]:
    body = re.sub(r"#[^\n]*", "", body)
    return [a.strip('"') for a in body.split() if a]


def parse_cmake(text: str, base_dir: str = "") -> dict:
    """Language standard, executable/library targets with their source files, include dirs and packages."""
    out: dict = {"std": None, "targets": {}, "include_dirs": [], "packages": []}
    for m in _CMD.finditer(text):
        cmd, args = m.group(1).lower(), _args(m.group(2))
        if not args:
            continue
        if cmd == "set" and args[0] == "CMAKE_CXX_STANDARD" and len(args) > 1 and args[1].isdigit():
            out["std"] = int(args[1])
        elif cmd in ("target_compile_features",):
            for a in args:
                mm = re.fullmatch(r"cxx_std_(\d+)", a)
                if mm:
                    out["std"] = int(mm.group(1))
        elif cmd in ("add_executable", "add_library"):
            name, rest = (
                args[0],
                [a for a in args[1:] if a.upper() not in ("STATIC", "SHARED", "MODULE", "OBJECT", "WIN32", "EXCLUDE_FROM_ALL")],
            )
            if "${" in " ".join(rest):
                rest = [a for a in rest if "${" not in a]  # variables we cannot expand
            out["targets"][name] = {
                "kind": "executable" if cmd == "add_executable" else "library",
                "sources": [posixpath.normpath(posixpath.join(base_dir, s)) for s in rest],
            }
        elif cmd in ("include_directories", "target_include_directories"):
            for a in args:
                if (
                    a.upper() in ("PUBLIC", "PRIVATE", "INTERFACE", "SYSTEM", "BEFORE", "AFTER")
                    or "${" in a
                    or a == args[0]
                    and cmd.startswith("target")
                ):
                    continue
                out["include_dirs"].append(posixpath.normpath(posixpath.join(base_dir, a)))
        elif cmd == "find_package":
            out["packages"].append(args[0])
    return out


def select_cmake_target(cmake: dict, files: set[str]) -> tuple[str | None, set[str] | None]:
    """The executable to migrate and the .cpp files it is built from (None when CMake lists no usable sources)."""
    exes = {n: t for n, t in cmake.get("targets", {}).items() if t["kind"] == "executable" and t["sources"]}
    if not exes:
        return None, None
    # prefer the executable whose sources are all present; first declared wins
    for name, t in exes.items():
        present = {s for s in t["sources"] if s in files}
        if present:
            libs = {s for n, lt in cmake["targets"].items() if lt["kind"] == "library" for s in lt["sources"] if s in files}
            return name, present | libs
    return None, None
