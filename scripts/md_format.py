#!/usr/bin/env python3
"""Markdown formatter/linter: enforces 80-column text and aligned tables,
plus markdownlint-cli's default structural rules.

Usage:
    md_format.py <file> [--check-only]

Default mode runs `markdownlint --fix` first (structural rules: trailing
whitespace, hard tabs, blank lines, heading style, pipe style, etc.), then
flags/fixes 80-column reflow and table alignment (which markdownlint-cli
cannot auto-fix), then re-checks both tools and reports anything that
remains. --check-only only reports violations from both tools and exits
non-zero if any were found, without touching the file.

HTML comments (`<!-- ... -->`, single-line or block), lines containing a
URL, and titles/headings (`#`...) are exempt from the 80-column rule and
are never broken/wrapped.

Requires `markdownlint-cli` on PATH (`npm install -g markdownlint-cli`).
"""

import argparse
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

MAX_WIDTH = 80

MARKDOWNLINT_CONFIG = Path(__file__).resolve().parent / ".markdownlint.jsonc"

FENCE_RE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW_RE = re.compile(r"^\s*\|?.*\|.*\|?\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+\.)(\s+)(.*)$")
BLOCKQUOTE_RE = re.compile(r"^(\s*)(>+)\s?(.*)$")
COMMENT_START_RE = re.compile(r"<!--")
COMMENT_END_RE = re.compile(r"-->")
URL_RE = re.compile(r"(?:https?://|ftp://|www\.)\S+", re.IGNORECASE)


def run_markdownlint(path, fix=False):
    """Run markdownlint-cli against `path` using the bundled config.

    Returns (ok, output_text). ok is True if markdownlint found no
    remaining violations (exit code 0). output_text is combined
    stdout/stderr, empty when clean.
    """
    if shutil.which("markdownlint") is None:
        return False, (
            "markdownlint-cli not found on PATH — install it with: "
            "npm install -g markdownlint-cli"
        )
    cmd = ["markdownlint", "--config", str(MARKDOWNLINT_CONFIG)]
    if fix:
        cmd.append("--fix")
    cmd.append(str(path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


class Violation:
    def __init__(self, line_no, kind, detail):
        self.line_no = line_no
        self.kind = kind
        self.detail = detail

    def __str__(self):
        return f"line {self.line_no}: [{self.kind}] {self.detail}"


def split_blocks(lines):
    """Split lines into a list of (kind, block_lines, start_index) tuples.

    kind is one of: "code", "comment", "table", "text".
    """
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if FENCE_RE.match(line):
            start = i
            block = [line]
            i += 1
            while i < n and not FENCE_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            if i < n:
                block.append(lines[i])
                i += 1
            blocks.append(("code", block, start))
            continue

        if COMMENT_START_RE.search(line):
            start = i
            block = [line]
            if not COMMENT_END_RE.search(line):
                i += 1
                while i < n and not COMMENT_END_RE.search(lines[i]):
                    block.append(lines[i])
                    i += 1
                if i < n:
                    block.append(lines[i])
            i += 1
            blocks.append(("comment", block, start))
            continue

        if (
            TABLE_ROW_RE.match(line)
            and i + 1 < n
            and TABLE_SEP_RE.match(lines[i + 1])
        ):
            start = i
            block = [line, lines[i + 1]]
            i += 2
            while i < n and lines[i].strip() and "|" in lines[i]:
                block.append(lines[i])
                i += 1
            blocks.append(("table", block, start))
            continue

        start = i
        block = [line]
        i += 1
        blocks.append(("text", block, start))

    return blocks


def check_text_block(block, start_index, violations):
    for offset, line in enumerate(block):
        if URL_RE.search(line):
            continue
        is_title = line.lstrip().startswith("#")
        if not is_title and len(line.rstrip("\n")) > MAX_WIDTH:
            violations.append(
                Violation(
                    start_index + offset + 1,
                    "line-too-long",
                    f"{len(line.rstrip(chr(10)))} columns (max {MAX_WIDTH})",
                )
            )


def is_paragraph_break(line):
    """Lines that must never be merged into a reflowed paragraph."""
    return (
        not line.strip()
        or line.lstrip().startswith("#")
        or LIST_ITEM_RE.match(line)
        or BLOCKQUOTE_RE.match(line)
        or URL_RE.search(line)
    )


def fix_text_block(block):
    """Reflow contiguous non-blank paragraph lines to MAX_WIDTH columns.

    Headings, blank lines, and lines containing a URL are left untouched
    (never merged, wrapped, or broken); list items keep their marker and
    are rewrapped with a hanging indent; blockquote lines keep their `>`
    marker repeated on every wrapped line; unless the item/quote itself
    contains a URL, in which case it too is left untouched.
    """
    out = []
    i = 0
    n = len(block)
    while i < n:
        raw_line = block[i].rstrip("\n")
        is_url_line = bool(URL_RE.search(raw_line))
        line = raw_line

        if not line.strip() or line.lstrip().startswith("#") or is_url_line:
            out.append(line + "\n")
            i += 1
            continue

        list_match = LIST_ITEM_RE.match(line)
        if list_match:
            indent, marker, _, rest = list_match.groups()
            initial_indent = f"{indent}{marker} "
            subsequent_indent = " " * len(initial_indent)
            para = [rest]
            i += 1
            while i < n and block[i].strip() and not is_paragraph_break(
                block[i]
            ):
                para.append(block[i].strip())
                i += 1
            wrapped = textwrap.fill(
                " ".join(para).strip(),
                width=MAX_WIDTH,
                initial_indent=initial_indent,
                subsequent_indent=subsequent_indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
            out.extend(l + "\n" for l in wrapped.split("\n"))
            continue

        quote_match = BLOCKQUOTE_RE.match(line)
        if quote_match:
            indent, marker, rest = quote_match.groups()
            quote_prefix = f"{indent}{marker} "
            para = [rest]
            i += 1
            while i < n and block[i].strip() and not is_paragraph_break(
                block[i]
            ):
                para.append(block[i].strip())
                i += 1
            wrapped = textwrap.fill(
                " ".join(para).strip(),
                width=MAX_WIDTH,
                initial_indent=quote_prefix,
                subsequent_indent=quote_prefix,
                break_long_words=False,
                break_on_hyphens=False,
            )
            out.extend(l + "\n" for l in wrapped.split("\n"))
            continue

        para = [line.strip()]
        i += 1
        while i < n and block[i].strip() and not is_paragraph_break(block[i]):
            para.append(block[i].strip())
            i += 1
        wrapped = textwrap.fill(
            " ".join(para).strip(),
            width=MAX_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
        )
        out.extend(l + "\n" for l in wrapped.split("\n"))

    return out


def parse_table(block):
    def split_row(row):
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]

    header = split_row(block[0])
    sep = split_row(block[1])
    rows = [split_row(r) for r in block[2:]]

    aligns = []
    for cell in sep:
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        elif left:
            aligns.append("left")
        else:
            aligns.append("none")

    return header, aligns, rows


def is_table_aligned(block):
    header, aligns, rows = parse_table(block)
    ncols = len(header)
    widths = [0] * ncols
    for row in [header] + rows:
        for idx in range(min(ncols, len(row))):
            widths[idx] = max(widths[idx], len(row[idx]))

    rebuilt = render_table(header, aligns, rows, widths)
    return rebuilt == [l.rstrip("\n") for l in block]


def render_table(header, aligns, rows, widths):
    def pad(cell, width, align):
        if align == "right":
            return cell.rjust(width)
        if align == "center":
            return cell.center(width)
        return cell.ljust(width)

    def sep_cell(width, align):
        if align == "center":
            return ":" + "-" * max(width - 2, 1) + ":"
        if align == "right":
            return "-" * max(width - 1, 1) + ":"
        if align == "left":
            return ":" + "-" * max(width - 1, 1)
        return "-" * width

    def render_row(row, aligns_local):
        cells = []
        for idx, w in enumerate(widths):
            cell = row[idx] if idx < len(row) else ""
            align = aligns_local[idx] if idx < len(aligns_local) else "none"
            cells.append(pad(cell, w, align))
        return "| " + " | ".join(cells) + " |"

    lines = [render_row(header, aligns)]
    lines.append(
        "| " + " | ".join(sep_cell(w, a) for w, a in zip(widths, aligns)) + " |"
    )
    for row in rows:
        lines.append(render_row(row, aligns))
    return lines


def check_table_block(block, start_index, violations):
    if not is_table_aligned(block):
        violations.append(
            Violation(start_index + 1, "table-not-aligned", "columns not aligned")
        )


def fix_table_block(block):
    header, aligns, rows = parse_table(block)
    ncols = len(header)
    widths = [0] * ncols
    for row in [header] + rows:
        for idx in range(min(ncols, len(row))):
            widths[idx] = max(widths[idx], len(row[idx]))
    return [l + "\n" for l in render_table(header, aligns, rows, widths)]


def check(lines):
    violations = []
    blocks = split_blocks(lines)
    for idx, (kind, block, start) in enumerate(blocks):
        if kind == "text":
            check_text_block(block, start, violations)
        elif kind == "table":
            check_table_block(block, start, violations)
            next_block = blocks[idx + 1][1] if idx + 1 < len(blocks) else None
            if next_block and next_block[0].strip():
                violations.append(
                    Violation(
                        start + len(block) + 1,
                        "table-missing-blank-line-after",
                        "table must be followed by a blank line",
                    )
                )
    return violations


def fix(lines):
    out = []
    blocks = split_blocks(lines)
    for idx, (kind, block, _start) in enumerate(blocks):
        if kind in ("code", "comment"):
            out.extend(block)
        elif kind == "table":
            out.extend(fix_table_block(block))
            next_block = blocks[idx + 1][1] if idx + 1 < len(blocks) else None
            if next_block and next_block[0].strip():
                out.append("\n")
        else:
            out.extend(fix_text_block(block))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="report violations without rewriting the file",
    )
    args = parser.parse_args()

    if shutil.which("markdownlint") is None:
        print(
            "markdownlint-cli not found on PATH — install it with: "
            "npm install -g markdownlint-cli"
        )
        sys.exit(1)

    if args.check_only:
        md_ok, md_output = run_markdownlint(args.file, fix=False)
        with open(args.file, encoding="utf-8") as f:
            lines = f.readlines()
        py_violations = check(lines)

        if md_output:
            print(md_output)
        if py_violations:
            print(f"{len(py_violations)} violation(s) found in {args.file}:")
            for v in py_violations:
                print(f"  {v}")
        if md_ok and not py_violations:
            print(f"No violations found in {args.file}")
        sys.exit(0 if (md_ok and not py_violations) else 1)

    # Python pass first: reflow, table alignment, and blank-line-after-table
    # normalization. This must run *before* markdownlint touches the file —
    # a table immediately followed by non-blank text (no blank line) gets
    # misparsed by markdownlint's own table parser as an extra malformed
    # table row (permanently flagged by MD055/MD056, never auto-fixed;
    # MD058 never gets a chance to add the missing blank line because the
    # line is no longer seen as text "after" the table). Python owns table
    # structure end to end, so it must be the one to guarantee that
    # separation exists before markdownlint ever parses the file.
    with open(args.file, encoding="utf-8") as f:
        lines = f.readlines()

    py_violations = check(lines)
    if py_violations:
        print(f"{len(py_violations)} violation(s) found in {args.file}:")
        for v in py_violations:
            print(f"  {v}")
        fixed = fix(lines)
        with open(args.file, "w", encoding="utf-8") as f:
            f.writelines(fixed)
    else:
        fixed = lines

    # Structural pass second: markdownlint fixes whitespace, blank lines,
    # heading/pipe style, etc. on the now well-formed file.
    _md_fix_ok, md_fix_output = run_markdownlint(args.file, fix=True)
    if md_fix_output:
        print(md_fix_output)

    # Final combined check: python re-scan (reflow/table-align/blank-line)
    # plus a markdownlint check-only pass (structural rules it couldn't
    # fix, and MD060 verifying the alignment fix_table_block just applied).
    with open(args.file, encoding="utf-8") as f:
        fixed = f.readlines()
    remaining_py = check(fixed)
    md_ok, md_check_output = run_markdownlint(args.file, fix=False)

    if md_check_output:
        print(md_check_output)
    if remaining_py:
        print(f"{len(remaining_py)} violation(s) remain after fix:")
        for v in remaining_py:
            print(f"  {v}")

    if md_ok and not remaining_py:
        print(f"Fixed and rewrote {args.file}")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
