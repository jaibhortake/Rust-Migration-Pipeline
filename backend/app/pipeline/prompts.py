RULES = """Type mapping rules:
- int/long long -> i64 (use i32 only if the source clearly means int32), unsigned -> u64/u32, double -> f64, bool -> bool
- std::vector<T>/list -> Vec<T>, std::string/str -> String, map/dict -> HashMap (BTreeMap if the output depends on order)
- None/nullptr -> Option<T>; exceptions -> Result<T, String>; raw pointers -> references or Box, no unsafe unless unavoidable
- Python ints are unbounded: use i128 or checked arithmetic where overflow is plausible; C++ signed overflow is UB, do not rely on wrapping
- Float printing must match the source's output format exactly
Use only the Rust standard library (no external crates). Read all input from stdin, write all output to stdout."""

DRIVER_SYSTEM = (
    "You write a small stdin/stdout driver around a function so it becomes a complete program. "
    "Reply with the COMPLETE program (original code plus driver) in one fenced code block and nothing else. "
    "The driver reads the function's arguments from stdin in a simple whitespace/line format and prints the result."
)

TESTS_SYSTEM = (
    "You design test inputs for a program that reads stdin. Reply with ONLY a JSON array of 6 to 10 strings; "
    "each string is the exact stdin for one run. Include edge cases (empty/minimal, large-ish, negative numbers). "
    "Keep each input valid for the program."
)

TRANSLATE_SYSTEM = (
    "You are an expert in translating {lang} to idiomatic, safe Rust. Behavior must match the original exactly, "
    "including output formatting. Reply with the complete src/main.rs in one ```rust fenced block, nothing else.\n\n"
    + RULES
)

FIX_COMPILE = "The Rust failed to compile. Fix it and return the complete corrected src/main.rs.\n\nCompiler output:\n{errors}"

FIX_MISMATCH = (
    "The Rust compiled but its output differs from the original program's output.\n"
    "stdin:\n{stdin}\nexpected stdout:\n{expected}\nactual stdout:\n{actual}\n"
    "Fix the Rust so it matches exactly and return the complete corrected src/main.rs."
)
