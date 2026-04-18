"""
_clean_and_run.py
Strips every non-ASCII character from failure_injection_suite.py,
then executes it in-process so there are no encoding issues.
"""
import sys, io, os, re, runpy

# ── force UTF-8 stdout so print() never hits cp1252 ─────────────────────────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(HERE, "failure_injection_suite.py")

# ── known replacements (preserves meaning) ──────────────────────────────────
REPLACEMENTS = {
    "\u2550": "=", "\u2500": "-", "\u2502": "|",
    "\u2013": "-", "\u2014": "--",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2192": "->", "\u2190": "<-", "\u2194": "<->",
    "\u26a0": "(!)", "\u2713": "(v)", "\u2717": "(x)",
    "\u00b7": ".", "\u20b9": "Rs.",
    "\u2554": "+", "\u2557": "+", "\u255a": "+", "\u255d": "+",
    "\u2551": "|",
    "\u2026": "...",
    "\u2248": "~=", "\u2264": "<=", "\u2265": ">=",
    "\u00b6": "P", "\u00a9": "(C)", "\u00ae": "(R)",
}

print("=== _clean_and_run: reading source ===")
with open(SRC, encoding="utf-8") as f:
    src = f.read()

for bad, good in REPLACEMENTS.items():
    src = src.replace(bad, good)

# fallback: any remaining non-ASCII -> '?'
clean = src.encode("ascii", "replace").decode("ascii")

# count substitutions
changed = sum(1 for a, b in zip(src, clean) if a != b)
print(f"=== Replaced {changed} non-ASCII chars. Writing clean copy... ===")

CLEAN_SRC = os.path.join(HERE, "_suite_clean.py")
with open(CLEAN_SRC, "w", encoding="utf-8") as f:
    f.write(clean)

print(f"=== Running {CLEAN_SRC} ===\n")

# Run the cleaned file, forwarding sys.argv
sys.argv = [CLEAN_SRC] + sys.argv[1:]
runpy.run_path(CLEAN_SRC, run_name="__main__")
