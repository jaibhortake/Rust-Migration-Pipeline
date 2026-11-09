from app.mapping.libraries import ALLOWED_CRATES

GENERAL_RULES = (
    """Rules:
- Behaviour must match the original exactly, including every byte of output formatting.
- Safe, idiomatic Rust: no `unsafe`, no global mutable state, &str/&[T] for borrowed parameters, Option/Result instead
  of null/exceptions, iterators where they keep the code clear.
- Read all input from stdin and write all output to stdout, like the original.
- Python ints never overflow: use i64 only when values are clearly bounded, otherwise i128 or num_bigint::BigInt.
- Python // and % floor toward negative infinity: use div_euclid / rem_euclid when operands can be negative.
- Python dict iteration follows insertion order; Rust HashMap does not. Keep the original order where output depends on it.
- Allowed crates (already declared in Cargo.toml when the contract lists them): """
    + ", ".join(ALLOWED_CRATES)
    + """.
  Do not use any other crate."""
)

DRIVER_SYSTEM = (
    "You write a small stdin/stdout driver around a function so it becomes a complete program. "
    "Reply with the COMPLETE program (original code unchanged plus the driver) in one fenced code block and nothing else. "
    "The driver reads the function's arguments from stdin in a simple whitespace/line format and prints the result "
    "deterministically."
)

TESTS_SYSTEM = (
    "You design test inputs for a program that reads stdin. Reply with ONLY a JSON array of 8 to 12 strings; each "
    "string is the exact stdin for one run. Cover normal cases, edge cases (empty/minimal, one element, duplicates, "
    "negative numbers, zero, large-ish values) and every branch you can see. Every input must be valid for the program."
)

TARGETED_SYSTEM = (
    "You design test inputs for a program that reads stdin. Lines marked with '>>' are never executed by the current "
    "tests. Reply with ONLY a JSON array of up to 6 strings, each the exact stdin for one run, chosen to execute the "
    "marked lines. Inputs must be valid for the program (same format as the examples)."
)

TRANSLATE_SYSTEM = (
    "You are a senior engineer migrating a {lang} codebase to Rust one module at a time, following a migration "
    "contract produced by static analysis. Reply with the complete Rust file in ONE ```rust fenced block and nothing "
    "else.\n\n" + GENERAL_RULES
)

MODULE_TASK = """Translate the {lang} module `{unit}` (files: {files}) into the Rust file `{target}`.
{role}

{contract}

Source:
{source}"""

ROLE_MODULE = (
    "This is a library module of the crate. Make every item other modules use `pub`. Refer to other modules "
    "with `use crate::<module>::<Item>;`. Do not write `mod` declarations and no `fn main`."
)
ROLE_ENTRY = (
    "This is the program entry, src/main.rs. It must contain `fn main`. `mod` declarations for the other "
    "modules are added automatically: do not write them; import with `use crate::<module>::<Item>;`."
)

FIX_COMPILE = """The crate failed to compile. Fix it.
Reply with every file you change, each in its own ```rust block whose FIRST line is `// file: src/<name>.rs`, complete
(not a diff). Do not add `mod` declarations to main.rs.

Compiler output:
{errors}"""

FIX_MISMATCH = """The crate compiles but its output differs from the original program on this (minimised) input.
stdin:
{stdin}
expected stdout (from running the original):
{expected}
actual stdout of the Rust program:
{actual}
{hints}
Find the behavioural difference and fix it. Reply with every file you change, each in its own ```rust block whose
FIRST line is `// file: src/<name>.rs`, complete (not a diff)."""

REFINE_CLIPPY = """All tests pass. Now remove these clippy warnings WITHOUT changing behaviour (the tests will be re-run
and the change is rejected if any output changes). Reply with every file you change, each in its own ```rust block whose
FIRST line is `// file: src/<name>.rs`, complete.

Warnings:
{warnings}"""

BASELINE_SYSTEM = (
    "Translate this program to Rust. Reply with the complete src/main.rs in one ```rust fenced block. Use only the standard library."
)


# ---------------------------------------------------------------- function-level verification

HARNESS_SYSTEM = (
    "You write a test harness that calls individual functions and class methods of an existing program directly. "
    "The harness reads calls from stdin, one per line: `<function-or-Class.method> <args...>` with whitespace-separated "
    "arguments (use a leading count for lists, e.g. `sum_list 3 1 2 3`). For each line it parses the arguments, makes the "
    "call (for a method: create a fresh object from the constructor arguments given on the same line, then call the "
    "method) and prints ONE line with the result, or `error` if the call raises/throws. Floats print with fixed 6 decimals; "
    "booleans as true/false; lists space-separated. Unknown names print `?`. Cover at most 15 callables, preferring "
    "pure functions and simple methods. Never modify the program's own code. Reply with ONLY the harness in one fenced "
    "code block."
)

HARNESS_CPP_RULES = (
    "The program's source file `{entry}` is ALREADY #included above your code (with its main renamed), so every type and "
    "function in it is visible. Do NOT include it again; include any standard or project headers you need. Write your own "
    "`int main()`."
)
HARNESS_PY_RULES = (
    "Import what you need from these project modules: {modules}. The entry module is `{entry_module}`; it is safe to "
    'import (its main code is guarded by `if __name__ == "__main__"`).'
)

UNIT_TESTS_SYSTEM = (
    "You design stdin inputs for a test harness. Reply with ONLY a JSON array of 6 to 10 strings; each string is the full "
    "stdin of one harness run, containing 3 to 12 call lines in the harness's format. Cover every callable, normal values, "
    "edge cases (empty lists, zero, negatives, repeated values, boundaries) and error cases."
)

RUST_HARNESS_TASK = """Translate this {lang} test harness into Rust as `src/harness.rs`.
It must expose `pub fn run()` that reads ALL of stdin and handles each call line exactly like the original harness
(same parsing, same output text and formatting, `error` where the original catches an exception).
The crate's items are available through `use crate::...`: modules are declared at the crate root; items defined in
`main.rs` are `crate::Name`; private items of modules are not reachable, so use only what the listing below shows.

Crate API:
{api}

Original harness:
```
{harness}
```"""

FIX_HARNESS = """The Rust harness did not compile. Fix `src/harness.rs` only. Reply with ONE ```rust block whose FIRST line is
`// file: src/harness.rs` containing the complete corrected file.

Compiler output:
{errors}"""

FIX_HARNESS_MISMATCH = """The Rust harness and the original harness print different results for these calls. First check the
Rust HARNESS against the original harness (argument parsing, output format); fix `src/harness.rs` if that is where the
difference comes from. Reply with ONE ```rust block whose FIRST line is `// file: src/harness.rs` containing the complete file.

stdin:
{stdin}
original harness output:
{expected}
Rust harness output:
{actual}"""
