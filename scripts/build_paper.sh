#!/usr/bin/env bash
# Build two PDFs from paper/main.tex:
#   paper/preview.pdf       clean, true pagination
#   paper/preview-diff.pdf  same content, changes vs the original highlighted
# pdf/ is the Overleaf mirror and stays read-only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD=/tmp/ai-docker/paperbuild
NIX=/nix/store/2gkq62yzbw9kplg5yb6yhf57ckhrhrsd-nix-2.34.7/bin/nix

rm -rf "$BUILD"
mkdir -p "$BUILD/graphics"
cp -r "$ROOT"/pdf/{IEEEtran.cls,diagrams,photos} "$BUILD"/
cp "$ROOT"/figures/*.pdf "$BUILD/graphics/"

# IEEEtran prints note and url fields verbatim. The exported bib carries Zotero
# noise there ("98 citations (Crossref/DOI) [2025-02-17]", access dates, long
# URLs) which costs roughly a page of references.
python3 - "$ROOT" "$BUILD" <<'PY'
import re, sys, pathlib
root, build = (pathlib.Path(p) for p in sys.argv[1:3])
DROP = ("note", "url", "urldate", "annotation", "abstract", "file", "keywords")
pattern = re.compile(r"^\s*(" + "|".join(DROP) + r")\s*=", re.I)

def clean(text):
    out, depth, skipping = [], 0, False
    for line in text.splitlines():
        if not skipping and pattern.match(line):
            skipping, depth = True, 0
        if skipping:
            depth += line.count("{") - line.count("}")
            if depth <= 0 and (line.rstrip().endswith(",") or line.count("}")):
                skipping = False
            continue
        out.append(line)
    return "\n".join(out) + "\n"

for name in ("references.bib", "manual-references.bib"):
    (build / name).write_text(clean((root / "pdf" / name).read_text()))
extra = (root / "paper" / "references_add.bib").read_text()
with (build / "manual-references.bib").open("a") as fh:
    fh.write("\n" + extra)
print("bib cleaned")
PY

main="$(cat "$ROOT/paper/main.tex")"
printf '%s' "$main" > "$BUILD/main.tex"
printf '\\def\\DIFFMODE{}\n%s' "$main" > "$BUILD/maindiff.tex"

cd "$BUILD"
for target in main maindiff; do
  "$NIX" shell nixpkgs#tectonic --command \
    tectonic -X compile "$target.tex" --keep-logs 2>&1 \
    | grep -viE '^note: (downloading|Rerun|Running)' | tail -6
done

cp "$BUILD/main.pdf" "$ROOT/paper/preview.pdf"
cp "$BUILD/maindiff.pdf" "$ROOT/paper/preview-diff.pdf"
"$NIX" shell nixpkgs#poppler-utils --command \
  sh -c 'pdfinfo main.pdf | grep Pages; pdfinfo maindiff.pdf | grep Pages'
