---
name: md-format
description: Formats a markdown file into a human-readable, linted style — aligns tables, wraps prose/list text to 80 columns (tables, HTML comments, titles/headings, and lines containing a URL are exempt and never broken), and strips comma thousands separators from numbers. Invoked by other skills as a formatting pass, not by a user-facing trigger phrase. This is a mechanical, deterministic pass with no judgment calls.
metadata:
  author: clara.muller
  model: low
---

# md-format

Formats a markdown file so it reads well as plain text: tables get their
columns aligned, and prose/list text is wrapped to 80 columns. This skill has
no trigger phrase of its own — other skills invoke it as a finishing pass
after they generate or edit markdown.

## When to use

- Invoked by another skill (e.g. a doc-writing or sync skill) right before
  it finalizes a markdown file.
- **Do NOT use** on non-markdown files, or inside fenced code blocks within a
  markdown file — code blocks are left untouched by design.

## Rules enforced

1. Table columns must be aligned (consistent cell widths, alignment markers
   from the separator row — `:---`, `---:`, `:---:` — preserved).
2. Prose and list text must not exceed 80 columns.
3. Rule 2 does not apply inside tables — a table cell can be any width.
4. Rule 2 does not apply to HTML comments (`<!-- ... -->`, single-line or
   block), titles/headings (`#`...), or any line containing a URL — these
   are never flagged and never broken/rewrapped, even when far over 80
   columns.
5. Numbers must not use a comma thousands separator — `10,000` is rewritten
   to `10000`, in prose, list items, table cells, and titles alike. Numbers
   inside a URL-exempt line (rule 4) are left as-is, since that whole line
   is never touched.

Fenced code blocks are never rewrapped, even if long.

## Inputs

- `file` — path to the markdown file to format (required).

## Steps

1. Run the linter/fixer on the target file (this skill runs under a
   low-effort model per its `metadata.model` setting — no larger model is
   needed for this mechanical, deterministic pass):

   ```
   python3 <skill-dir>/scripts/md_format.py <file>
   ```

   The script first flags every violation it finds (line number + reason),
   then rewrites the file with corrections applied, then re-checks the
   result and reports if anything remains unfixed. Pass `--check-only` to
   report without modifying the file.
2. Relay the subagent's report (violations found, violations fixed, any
   that couldn't be auto-fixed) back to the caller.
3. Verify: after the run, `python3 scripts/md_format.py <file> --check-only`
   should exit `0` with "No violations found". If it doesn't, surface the
   remaining violations — don't silently consider the pass done.

## Output

The target markdown file rewritten in place, plus a short report of what was
flagged and fixed (or a note that the file was already clean).

## Tests

`scripts/test_md_format.py` is a unit-test suite for the linter/fixer
(paragraph wrapping, list-item indent preservation, heading/code-block
exemption, table alignment and alignment-marker preservation, URL/comment
exemption, comma-thousands-separator stripping, block splitting). Run it
after changing `md_format.py`:

```
python3 -m unittest scripts/test_md_format.py -v
```

All tests must pass before the script is trusted to run unattended.

## Notes & guardrails

- The script never touches fenced code blocks (` ``` ` / `~~~`) regardless
  of line width.
- Titles/headings (a line starting with `#`) are never wrapped and never
  flagged for length, regardless of width — only the number-comma rule
  (rule 5) still applies to them.
- HTML comments (`<!-- ... -->`) are detected as their own block (single- or
  multi-line) and passed through byte-for-byte, like code blocks.
- A line matched as containing a URL (`http://`, `https://`, `ftp://`, or
  `www.`) is emitted verbatim: it is never merged into paragraph reflow, so
  prose immediately before/after it still wraps normally on its own lines.
- Comma-thousands detection requires 1-3 leading digits followed by one or
  more `,ddd` groups (optionally a decimal tail), so it won't misfire on an
  ordinary comma-separated list like "a, b, and c".
- Table detection requires a header row immediately followed by a valid
  separator row (`|---|`, with optional `:` alignment markers); anything
  else is treated as prose.
- This is a personal skill (`~/.claude/skills/md-format`) — it is not
  scoped to any one repo's workspace rules, but the caller invoking it is
  still responsible for its own repo's git/branch rules (this skill only
  rewrites file content, it never runs git).
