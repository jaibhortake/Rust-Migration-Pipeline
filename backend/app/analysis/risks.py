"""Migration risks: constructs whose Rust translation is hard or whose semantics silently differ.

Each rule says why it matters and what the Rust strategy is; the strategy is also given to the translator.
"""

import re
from dataclasses import asdict, dataclass

from app.analysis.symbols import FileSymbols

SEVERITY_WEIGHT = {"high": 8, "medium": 3, "low": 1}


@dataclass
class Risk:
    rule: str
    severity: str  # high | medium | low
    title: str
    file: str
    line: int
    why: str
    strategy: str

    def to_dict(self) -> dict:
        return asdict(self)


# (rule id, severity, regex, title, why, strategy)
PY_RULES = [
    (
        "floor-div",
        "medium",
        r"(?<![/=])//(?!=)|//=",
        "Floor division / modulo on possibly negative numbers",
        "Python // and % round toward negative infinity; Rust / and % truncate toward zero (-7//2 is -4 in Python, -3 in Rust).",
        "Use i64::div_euclid / rem_euclid (equal to Python for positive divisors).",
    ),
    (
        "modulo",
        "medium",
        r"[\w)\]]\s*%\s*[\w(]",
        "Modulo operator",
        "Python % takes the sign of the divisor; Rust % takes the sign of the dividend.",
        "Use rem_euclid when the left side can be negative.",
    ),
    (
        "big-int",
        "high",
        r"\*\*\s*\d{2,}|\bfactorial\b|\bmath\.comb\b|\d{19,}|\bpow\(\s*\w+\s*,\s*\w+\s*\)(?!\s*%)",
        "Arbitrary-precision integers",
        "Python ints never overflow; Rust i64 panics (debug) or wraps (release).",
        "Use i128 or checked arithmetic when bounded; num_bigint::BigInt when values can grow without bound.",
    ),
    (
        "eval",
        "high",
        r"\b(eval|exec|compile)\s*\(",
        "eval / exec",
        "Runs code built at runtime; Rust has no interpreter.",
        "Replace with an explicit parser or a match on known commands.",
    ),
    (
        "reflection",
        "high",
        r"\b(getattr|setattr|hasattr|delattr)\s*\(|__dict__|\bvars\(",
        "Reflection / dynamic attributes",
        "Attributes chosen at runtime have no static equivalent.",
        "Use a HashMap<String, Value> or an enum of known fields.",
    ),
    (
        "metaclass",
        "high",
        r"metaclass\s*=|__new__\s*\(",
        "Metaclass / __new__",
        "Class creation hooks have no Rust counterpart.",
        "Generate code with a macro or write the types out explicitly.",
    ),
    (
        "monkeypatch",
        "high",
        r"^\s*[A-Z]\w*\.\w+\s*=\s*\w+\s*$|^\s*\w+\.\w+\s*=\s*lambda\b",
        "Possible monkey patching",
        "Replacing methods at runtime.",
        "Use a trait object or a function pointer field.",
    ),
    (
        "dict-order",
        "medium",
        r"for\s+\w+(\s*,\s*\w+)?\s+in\s+\w+\.(items|keys|values)\(\)",
        "Iteration over a dict",
        "Python dicts keep insertion order; Rust HashMap iteration order is random, so printed output may differ.",
        "Use a Vec of (key, value) pairs plus an index map, or BTreeMap if sorted order is acceptable.",
    ),
    (
        "set-order",
        "medium",
        r"for\s+\w+\s+in\s+(set\(|\{[^:}]+\})",
        "Iteration over a set",
        "Output that depends on set iteration order is not reproducible in Rust's HashSet.",
        "Use BTreeSet or sort before iterating.",
    ),
    (
        "round",
        "medium",
        r"\bround\(",
        "round()",
        "Python round() uses banker's rounding (round(2.5) == 2); Rust f64::round rounds half away from zero.",
        "Implement round-half-even explicitly when ties are possible.",
    ),
    (
        "float-print",
        "medium",
        r"print\([^)]*\b\d+\.\d+|print\([^)]*[^/]/(?!/)",
        "Printing floats",
        "Python prints floats like 1e+16 and 0.1 in shortest repr; Rust's {} differs for large/small magnitudes.",
        "Format explicitly (e.g. {:.6}) to match the original or write a repr-compatible formatter.",
    ),
    (
        "generator",
        "medium",
        r"\byield\b",
        "Generators",
        "Rust has no stable generators.",
        "Implement Iterator on a struct holding the generator's state, or collect into a Vec.",
    ),
    (
        "global",
        "medium",
        r"^\s*(global|nonlocal)\s",
        "global / nonlocal state",
        "Mutable globals are unsafe in Rust.",
        "Pass state explicitly, or use a struct; thread_local!/OnceLock if needed.",
    ),
    (
        "varargs",
        "medium",
        r"def\s+\w+\([^)]*\*\*?\w+",
        "*args / **kwargs",
        "Variadic and keyword arguments do not exist in Rust.",
        "Use slices, Option parameters or a builder/options struct.",
    ),
    (
        "exceptions",
        "medium",
        r"^\s*(try:|raise\s)",
        "Exceptions",
        "Exceptions unwind across calls; Rust uses Result values.",
        "Return Result<T, E> and propagate with ?.",
    ),
    (
        "str-index",
        "low",
        r"\w+\[\s*-?\d*\s*:\s*-?\d*\s*\]|\bord\(|\bchr\(",
        "String slicing / character codes",
        "Python indexes strings by Unicode code point; Rust strings are UTF-8 bytes.",
        "Work on Vec<char> or .chars() for non-ASCII text; bytes for ASCII.",
    ),
    (
        "threads",
        "high",
        r"\bimport\s+(threading|multiprocessing|asyncio)\b|from\s+(threading|multiprocessing|asyncio)\b",
        "Concurrency",
        "Shared mutable state must be proven safe in Rust.",
        "std::thread with Arc<Mutex<T>> or channels.",
    ),
    (
        "random",
        "high",
        r"\bimport\s+random\b|from\s+random\b",
        "Randomness",
        "Output cannot be compared against the original, and no random crate is available offline.",
        "Inject a seedable PRNG (e.g. a small xorshift) and compare with a fixed seed.",
    ),
]

CPP_RULES = [
    (
        "manual-memory",
        "high",
        r"\bnew\s+\w|\bdelete\s*(\[\])?\s*\w|\bmalloc\s*\(|\bfree\s*\(",
        "Manual memory management",
        "new/delete and malloc/free must become owned values.",
        "Box<T>, Vec<T>, Rc<RefCell<T>> for shared ownership.",
    ),
    (
        "pointer-arith",
        "high",
        r"(^|[=(,;{]|return)\s*\*\s*\(\s*\w+\s*[+-]|\w+\s*=\s*\w+->(next|prev|left|right|parent|child)\b|\bNode\s*\*",
        "Pointer arithmetic / linked structures",
        "Raw pointer walking and self-referential structures fight the borrow checker.",
        "Use indices into a Vec (arena), Option<Box<Node>> or slices.",
    ),
    (
        "unsafe-cast",
        "high",
        r"\breinterpret_cast\b|\bconst_cast\b|\(\s*(int|char|long|void)\s*\*\s*\)",
        "Unsafe casts",
        "Type punning has no safe equivalent.",
        "Use explicit conversions (from_le_bytes, as for numerics) or redesign.",
    ),
    ("union", "high", r"\bunion\s+\w*\s*\{", "Unions", "Untagged unions require unsafe.", "Use a Rust enum (tagged union)."),
    ("goto", "high", r"\bgoto\s+\w+", "goto", "Rust has no goto.", "Restructure with loops and labeled break/continue."),
    (
        "macro",
        "medium",
        r"^\s*#\s*define\s+\w+\(",
        "Function-like macros",
        "Textual macros are not type checked.",
        "Use generic functions or macro_rules!.",
    ),
    (
        "template",
        "medium",
        r"\btemplate\s*<",
        "Templates",
        "Templates are duck-typed at instantiation.",
        "Use generics with explicit trait bounds (T: Ord + Clone ...).",
    ),
    ("exceptions", "medium", r"\bthrow\b|\btry\s*\{", "Exceptions", "Rust has no exceptions.", "Return Result<T, E>."),
    (
        "threads",
        "high",
        r"#include\s*<(thread|mutex|atomic|future)>",
        "Concurrency",
        "Data races are compile errors in Rust.",
        "std::thread with Arc<Mutex<T>>, atomics or channels.",
    ),
    (
        "global-mut",
        "medium",
        r"^(static\s+)?(int|long|double|char|bool|std::\w+|vector<[^>]+>)\s+\w+(\s*\[[^\]]*\])?\s*(=[^;]*)?;\s*$",
        "Mutable global state",
        "Mutable statics need unsafe.",
        "Move into a struct passed by &mut, or thread_local!/OnceLock.",
    ),
    (
        "uninit",
        "low",
        r"^\s*(int|long|double|float|char)\s+\w+\s*;\s*$",
        "Uninitialised variables",
        "Rust requires initialisation; C++ reads of uninitialised values are UB.",
        "Initialise at declaration.",
    ),
    (
        "unsigned-wrap",
        "medium",
        r"\bunsigned\b|\bsize_t\b|\buint\d+_t\b",
        "Unsigned arithmetic",
        "Unsigned underflow wraps in C++ but panics in debug Rust.",
        "Use wrapping_sub / checked_sub where wraparound is relied on.",
    ),
    (
        "printf",
        "low",
        r"\bprintf\s*\(|\bscanf\s*\(",
        "printf / scanf",
        "Format specifiers must be matched exactly.",
        "Translate each specifier to format! (e.g. %.2f -> {:.2}).",
    ),
    (
        "iomanip",
        "low",
        r"\bsetprecision\b|\bfixed\b|\bsetw\b",
        "Stream formatting",
        "Stream manipulators are stateful.",
        "Apply the precision/width on every affected write!.",
    ),
    (
        "random",
        "high",
        r"#include\s*<random>|\brand\s*\(",
        "Randomness",
        "Output cannot be compared against the original.",
        "Inject a seedable PRNG and compare with a fixed seed.",
    ),
    (
        "char-arith",
        "low",
        r"'[a-zA-Z0-9]'\s*[-+]|[-+]\s*'[a-zA-Z0-9]'",
        "Character arithmetic",
        "chars are not integers in Rust.",
        "Use bytes (b'a') and `as u8`/`as char` conversions.",
    ),
]


def _line_hits(code: str, pattern: str) -> list[int]:
    rx = re.compile(pattern, re.MULTILINE)
    out = []
    for i, line in enumerate(code.splitlines(), 1):
        s = line.strip()
        if s.startswith(("#", "//")) and not s.startswith(("#define", "# define", "#include")):
            continue
        if rx.search(line):
            out.append(i)
    return out


def find_risks(language: str, path: str, code: str, symbols: FileSymbols) -> list[Risk]:
    rules = PY_RULES if language == "python" else CPP_RULES
    risks: list[Risk] = []
    is_header = path.lower().endswith((".h", ".hpp", ".hh", ".hxx"))
    for rule, sev, pat, title, why, strategy in rules:
        if is_header and rule in ("uninit", "global-mut"):
            continue  # class members and extern declarations, not variables
        lines = _line_hits(code, pat)
        # one finding per rule per file, at the first line; count noted in the title
        if lines:
            more = f" ({len(lines)} places)" if len(lines) > 1 else ""
            risks.append(Risk(rule, sev, title + more, path, lines[0], why, strategy))

    for c in symbols.classes:
        if len(c.bases) > 1 and not c.is_exception:
            risks.append(
                Risk(
                    "multiple-inheritance",
                    "high",
                    f"Multiple inheritance in {c.name}",
                    path,
                    c.line,
                    "Rust has no inheritance at all, and diamond hierarchies need redesign.",
                    "One trait per base interface; share data by composition.",
                )
            )
        if c.is_template:
            pass  # covered by the template rule
    for f in symbols.functions:
        if f.recursive:
            risks.append(
                Risk(
                    "recursion",
                    "low",
                    f"Recursion in {f.name}",
                    path,
                    f.line,
                    "Deep recursion can overflow the stack (Rust's main thread stack is 8 MB on Linux, 1 MB on Windows).",
                    "Keep it recursive for shallow depth; otherwise use an explicit stack or memo table.",
                )
            )
        if f.complexity >= 15:
            risks.append(
                Risk(
                    "complex-function",
                    "medium",
                    f"High complexity in {f.name} ({f.complexity})",
                    path,
                    f.line,
                    "Long branching functions are where translations drift.",
                    "Translate faithfully first; refactor only after behaviour is verified.",
                )
            )
    return risks


def risk_score(risks: list[Risk]) -> int:
    return sum(SEVERITY_WEIGHT[r.severity] for r in risks)
