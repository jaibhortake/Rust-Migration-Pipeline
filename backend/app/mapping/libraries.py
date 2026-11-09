"""Library / header mapping: what each C++ header or Python module becomes in Rust.

kind: std (standard library), crate (one of ALLOWED_CRATES, prefetched in the sandbox image),
manual (no direct equivalent; reimplement), unsupported (blocks verification, e.g. randomness, network, GUI).
"""

from dataclasses import asdict, dataclass

# Keep in sync with sandbox/prefetch/Cargo.toml.
ALLOWED_CRATES = {
    "num-bigint": 'num-bigint = "0.4"',
    "num-traits": 'num-traits = "0.2"',
    "num-integer": 'num-integer = "0.1"',
    "regex": 'regex = "1"',
    "serde": 'serde = { version = "1", features = ["derive"] }',
    "serde_json": 'serde_json = "1"',
    "itertools": 'itertools = "0.13"',
}


@dataclass
class LibMapping:
    source: str
    target: str
    kind: str  # std | crate | manual | unsupported
    crates: list[str]
    confidence: str  # high | medium | low
    note: str
    used_in: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _m(target, kind="std", crates=(), confidence="high", note=""):
    return {"target": target, "kind": kind, "crates": list(crates), "confidence": confidence, "note": note}


CPP = {
    "iostream": _m("std::io (stdin().lock().lines(), print!/println!)", note="Lock stdout and use a BufWriter for heavy output."),
    "cstdio": _m("std::io + format!", note="printf specifiers map to format! specifiers."),
    "string": _m("String / &str"),
    "string_view": _m("&str"),
    "vector": _m("Vec<T>"),
    "array": _m("[T; N]"),
    "deque": _m("std::collections::VecDeque"),
    "list": _m("std::collections::LinkedList (prefer Vec/VecDeque)", confidence="medium"),
    "forward_list": _m("Vec<T> or Option<Box<Node>>", confidence="medium"),
    "map": _m("std::collections::BTreeMap", note="Ordered, like std::map."),
    "unordered_map": _m("std::collections::HashMap"),
    "set": _m("std::collections::BTreeSet"),
    "unordered_set": _m("std::collections::HashSet"),
    "queue": _m(
        "VecDeque (queue) / BinaryHeap (priority_queue)",
        note="priority_queue is a max-heap like BinaryHeap; with std::greater wrap items in std::cmp::Reverse.",
    ),
    "stack": _m("Vec<T> (push/pop)"),
    "algorithm": _m(
        "slice and iterator methods (sort, sort_unstable, binary_search, iter().max(), retain, dedup)",
        note="std::sort is unstable; use sort_unstable or sort (stable) — both give the same result for total orders.",
    ),
    "numeric": _m("iter().sum(), fold, gcd via num-integer or a helper", confidence="high"),
    "cmath": _m("f64 methods (sqrt, powi, powf, abs, floor)"),
    "math.h": _m("f64 methods"),
    "climits": _m("i32::MAX, i64::MIN, ..."),
    "limits": _m("i32::MAX, f64::INFINITY, ..."),
    "cstdint": _m("i8..i64, u8..u64"),
    "cstring": _m("slices and String methods"),
    "cstdlib": _m("std::process::exit, i32::abs, str::parse", confidence="medium"),
    "utility": _m("tuples, std::mem::swap"),
    "tuple": _m("tuples"),
    "functional": _m("closures, Box<dyn Fn>"),
    "memory": _m("Box (unique_ptr), Rc/Arc (shared_ptr), Weak"),
    "optional": _m("Option<T>"),
    "variant": _m("enum"),
    "sstream": _m("String + split_whitespace / format!"),
    "fstream": _m("std::fs::File + BufReader", note="The sandbox has an empty filesystem; file I/O is not verifiable."),
    "iomanip": _m("format! width/precision ({:>8}, {:.3})"),
    "bitset": _m("u64 bit operations or Vec<bool>", confidence="medium"),
    "iterator": _m("Iterator trait"),
    "chrono": _m("std::time::{Instant, Duration}", confidence="medium", note="Timing output is not comparable."),
    "thread": _m("std::thread"),
    "mutex": _m("std::sync::Mutex"),
    "atomic": _m("std::sync::atomic"),
    "future": _m("std::thread + channels", confidence="low"),
    "cassert": _m("assert!"),
    "stdexcept": _m("Result<T, E> with an error enum"),
    "exception": _m("Result<T, E> with an error enum"),
    "regex": _m("regex::Regex", "crate", ["regex"], note="ECMAScript-specific features may differ."),
    "random": _m(
        "seeded PRNG written by hand", "unsupported", confidence="low", note="No rand crate offline; outputs are not reproducible anyway."
    ),
    "concepts": _m("trait bounds (T: Trait) and where-clauses", confidence="medium", note="A C++20 concept becomes a trait."),
    "ranges": _m("iterator adapters (map, filter, take, collect)", confidence="medium"),
    "type_traits": _m("generics with trait bounds; std::is_same_v checks become trait impls or match", confidence="medium"),
    "bits/stdc++.h": _m("std (imports chosen per use)", confidence="medium"),
}

PY = {
    "sys": _m("std::io / std::env / std::process", note="sys.setrecursionlimit has no equivalent: watch stack depth."),
    "math": _m("f64 methods and consts (std::f64::consts::PI)"),
    "collections": _m(
        "HashMap / VecDeque / BTreeMap (Counter -> HashMap<K, usize>, defaultdict -> entry API)",
        note="OrderedDict / dict insertion order needs an index map.",
    ),
    "heapq": _m("std::collections::BinaryHeap with std::cmp::Reverse", note="heapq is a MIN-heap; BinaryHeap is a MAX-heap."),
    "bisect": _m("slice::partition_point / binary_search"),
    "itertools": _m("itertools crate", "crate", ["itertools"], "medium"),
    "functools": _m("lru_cache -> HashMap memo, reduce -> fold, cmp_to_key -> sort_by", confidence="medium"),
    "operator": _m("closures"),
    "re": _m("regex::Regex", "crate", ["regex"], "medium", "No backreferences/lookaround in the regex crate."),
    "json": _m("serde_json", "crate", ["serde", "serde_json"], "medium", "Key order: serde_json sorts unless preserve_order."),
    "typing": _m("Rust types / generics"),
    "dataclasses": _m("#[derive(Debug, Clone, PartialEq)] struct"),
    "enum": _m("enum"),
    "abc": _m("trait"),
    "copy": _m("Clone"),
    "string": _m("char methods (is_ascii_lowercase, ...) and literals"),
    "fractions": _m("hand-written Rational over num-integer gcd", "manual", ["num-integer"], "medium"),
    "decimal": _m("fixed-point i128 or hand-written decimal", "manual", confidence="low"),
    "statistics": _m("hand-written mean/median", "manual", confidence="medium"),
    "time": _m("std::time", confidence="medium", note="Timing output is not comparable."),
    "os": _m("std::env / std::fs", confidence="medium"),
    "pathlib": _m("std::path::PathBuf", confidence="medium"),
    "threading": _m("std::thread + Arc<Mutex<T>>", confidence="medium"),
    "queue": _m("std::sync::mpsc channels / VecDeque", confidence="medium"),
    "random": _m(
        "seeded PRNG written by hand", "unsupported", confidence="low", note="No rand crate offline; outputs are not reproducible anyway."
    ),
    "datetime": _m("hand-written date arithmetic", "manual", confidence="low"),
    "numpy": _m("Vec<f64> loops (ndarray is not available offline)", "manual", confidence="low"),
    "pandas": _m("no equivalent", "unsupported", confidence="low"),
    "requests": _m("network access is disabled in the sandbox", "unsupported", confidence="low"),
    "socket": _m("std::net (network disabled in the sandbox)", "unsupported", confidence="low"),
    "asyncio": _m("std::thread (no async runtime available offline)", "manual", confidence="low"),
    "math.comb": _m("num-bigint / hand-written", "crate", ["num-bigint"], "medium"),
}

UNKNOWN = _m("no known mapping", "manual", confidence="low", note="Third-party library: needs a manual decision.")


def map_libraries(language: str, used: dict[str, list[str]], big_ints: bool) -> list[LibMapping]:
    """used: library name -> files that use it."""
    table = CPP if language == "cpp" else PY
    out = []
    for name, files in sorted(used.items()):
        key = name if language == "cpp" else name.split(".")[0]
        spec = table.get(key, UNKNOWN)
        out.append(LibMapping(name, spec["target"], spec["kind"], list(spec["crates"]), spec["confidence"], spec["note"], sorted(files)))
    if big_ints and language == "python":
        out.append(
            LibMapping(
                "int (arbitrary precision)",
                "num_bigint::BigInt",
                "crate",
                ["num-bigint", "num-traits"],
                "medium",
                "Only where values can exceed i64/i128.",
                [],
            )
        )
    return out


def crates_for(mappings: list[dict]) -> list[str]:
    """Cargo dependency lines for the crates the (possibly user-edited) mappings use."""
    names: list[str] = []
    for m in mappings:
        if m.get("kind") in ("crate", "manual"):
            for c in m.get("crates", []):
                if c in ALLOWED_CRATES and c not in names:
                    names.append(c)
    return [ALLOWED_CRATES[c] for c in names]
