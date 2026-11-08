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
