"""Type mapping: source types found in the code and the Rust type each should become."""

import re
from dataclasses import asdict, dataclass


@dataclass
class TypeMapping:
    source: str
    target: str
    note: str
    count: int

    def to_dict(self) -> dict:
        return asdict(self)


# (regex, source label, rust target, note)
CPP_TYPES = [
    (r"\blong\s+long\b", "long long", "i64", ""),
    (r"\bunsigned\s+long\s+long\b|\buint64_t\b", "unsigned long long / uint64_t", "u64", "Wrapping must be explicit."),
    (r"\bsize_t\b", "size_t", "usize", "Subtracting below zero panics in debug builds."),
    (r"\bunsigned(\s+int)?\b(?!\s+long)", "unsigned int", "u32", ""),
    (r"(?<![\w:])int(?!\w)", "int", "i32", "Use i64 if intermediate values can exceed 2^31."),
    (r"\blong\b(?!\s+long)", "long", "i64", "64-bit on Linux, 32-bit on Windows in C++."),
    (r"\bdouble\b", "double", "f64", ""),
    (r"\bfloat\b", "float", "f32", ""),
    (r"\bchar\b", "char", "u8", "C++ char is a byte; Rust char is a Unicode scalar."),
    (r"\bbool\b", "bool", "bool", ""),
    (r"\bstd::string\b|\bstring\b", "std::string", "String", "&str for read-only parameters."),
    (r"\bstd::string_view\b|\bstring_view\b", "std::string_view", "&str", ""),
    (r"\bvector\s*<", "std::vector<T>", "Vec<T>", "&[T] / &mut [T] for parameters."),
    (r"\barray\s*<", "std::array<T, N>", "[T; N]", ""),
    (r"\bunordered_map\s*<", "std::unordered_map<K, V>", "HashMap<K, V>", ""),
    (r"(?<!unordered_)\bmap\s*<", "std::map<K, V>", "BTreeMap<K, V>", "Keeps sorted iteration order."),
    (r"\bunordered_set\s*<", "std::unordered_set<T>", "HashSet<T>", ""),
    (r"(?<!unordered_)\bset\s*<", "std::set<T>", "BTreeSet<T>", ""),
    (r"\bpair\s*<", "std::pair<A, B>", "(A, B)", ""),
    (r"\btuple\s*<", "std::tuple<...>", "(...)", ""),
    (r"\boptional\s*<", "std::optional<T>", "Option<T>", ""),
    (r"\bunique_ptr\s*<", "std::unique_ptr<T>", "Box<T>", ""),
    (r"\bshared_ptr\s*<", "std::shared_ptr<T>", "Rc<RefCell<T>> (Arc<Mutex<T>> across threads)", ""),
    (r"\bweak_ptr\s*<", "std::weak_ptr<T>", "Weak<RefCell<T>>", ""),
    (r"\bdeque\s*<", "std::deque<T>", "VecDeque<T>", ""),
    (r"\bqueue\s*<", "std::queue<T>", "VecDeque<T>", ""),
    (r"\bstack\s*<", "std::stack<T>", "Vec<T>", ""),
    (r"\bpriority_queue\s*<", "std::priority_queue<T>", "BinaryHeap<T>", "Wrap in Reverse for std::greater."),
    (r"\bfunction\s*<", "std::function<F>", "Box<dyn Fn(..)>", ""),
    (r"\w\s*\*\s*\w", "T* (raw pointer)", "&T / &mut T / Option<Box<T>> / index", "Pick by ownership; never *mut T."),
    (r"\bconst\s+\w[\w:<>, ]*&", "const T&", "&T", ""),
    (r"\bnullptr\b|\bNULL\b", "nullptr", "None (Option<T>)", ""),
]

PY_TYPES = [
    (r"\b\d+\b|\bint\(", "int", "i64", "i128 / BigInt when values can exceed 2^63."),
    (r"\b\d+\.\d+\b|\bfloat\(", "float", "f64", ""),
    (r"['\"]|\bstr\(", "str", "String", "&str for parameters."),
    (r"\bTrue\b|\bFalse\b|\bbool\(", "bool", "bool", ""),
    (r"\[\s*\]|\blist\(|\[[^\]]+\]", "list", "Vec<T>", "Heterogeneous lists need an enum."),
    (r"\{\s*\}|\bdict\(|\{[^}]*:[^}]*\}", "dict", "HashMap<K, V>", "Insertion order is NOT kept; see dict-order risk."),
    (r"\bset\(|\{[^:}]+\}", "set", "HashSet<T>", "BTreeSet when iteration order matters."),
    (r"\btuple\(|\(\s*\w+\s*,\s*\w+", "tuple", "(A, B, ...)", ""),
    (r"\bNone\b", "None", "Option<T>", ""),
    (r"\bdeque\(", "collections.deque", "VecDeque<T>", ""),
    (r"\bCounter\(", "collections.Counter", "HashMap<K, usize>", ""),
    (r"\bdefaultdict\(", "collections.defaultdict", "HashMap with entry().or_default()", ""),
    (r"\bheapq\.", "heapq (min-heap)", "BinaryHeap<Reverse<T>>", ""),
    (r"\bbytes\(|\bb['\"]", "bytes", "Vec<u8> / &[u8]", ""),
    (r"\blambda\b", "lambda", "closure |x| ...", ""),
]


def map_types(language: str, code_by_file: dict[str, str]) -> list[TypeMapping]:
    rules = CPP_TYPES if language == "cpp" else PY_TYPES
    code = "\n".join(_strip_comments(language, c) for c in code_by_file.values())
    out = []
    for rx, src, target, note in rules:
        n = len(re.findall(rx, code))
        if n:
            out.append(TypeMapping(src, target, note, n))
    return out


def _strip_comments(language: str, code: str) -> str:
    if language == "cpp":
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        return re.sub(r"//[^\n]*|^\s*#\s*include[^\n]*", "", code, flags=re.MULTILINE)
    return re.sub(r"#[^\n]*", "", code)
