---
name: md-format
description: Formats a markdown file into a human-readable, linted style — aligns tables, wraps prose/list text to 80 columns (tables, HTML comments, titles/headings, and lines containing a URL are exempt and never broken), and applies markdownlint-cli's default structural rules (whitespace, blank lines, heading/list/code-fence style, etc.). Invoked by other skills as a formatting pass, not by a user-facing trigger phrase. This is a mechanical, deterministic pass with no judgment calls.
metadata:
  author: clara.muller
  model: low
---

# md-format

Formats a markdown file so it reads well as plain text: tables get their
columns aligned, prose/list text is wrapped to 80 columns, and
`markdownlint-cli`'s default structural rules (trailing whitespace, hard
tabs, blank-line spacing, heading/list-marker/code-fence style, etc.) are
applied. This skill has no trigger phrase of its own — other skills invoke
it as a finishing pass after they generate or edit markdown.

## Requirements

`markdownlint-cli` must be installed and on `PATH`:

```
npm install -g markdownlint-cli
```

The script fails fast with a clear error if it's missing.

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

Fenced code blocks are never rewrapped, even if long.

On top of rules 1–4 (owned by this skill's own Python logic, since
`markdownlint-cli` cannot auto-fix either 80-col reflow or table alignment
— see "Notes & guardrails"), `markdownlint-cli`'s default rule set is
applied for everything else: no trailing whitespace, no hard tabs, no more
than one consecutive blank line, consistent heading/list-marker/code-fence
style, blank lines around headings/lists/fences/tables, a single trailing
newline, and so on.

## Inputs

- `file` — path to the markdown file to format (required).

## Steps

1. Run the linter/fixer on the target file (this skill runs under a
   low-effort model per its `metadata.model` setting — no larger model is
   needed for this mechanical, deterministic pass):

   ```
   python3 <skill-dir>/scripts/md_format.py <file>
   ```

   The script runs a combined pipeline: `markdownlint --fix` first
   (structural rules — whitespace, blank lines, heading/pipe style, etc.),
   then this skill's own reflow/table-alignment fixer (which
   `markdownlint-cli` cannot auto-fix), then a final check from both tools
   to report anything that remains unfixed. Pass `--check-only` to report
   without modifying the file.
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
exemption, block splitting, and the `markdownlint-cli` wrapper — mocked for
the main suite, plus one real-binary integration test that's skipped when
`markdownlint` isn't installed). Run it after changing `md_format.py`:

```
python3 -m unittest scripts/test_md_format.py -v
```

All tests must pass before the script is trusted to run unattended.

## Notes & guardrails

- The script never touches fenced code blocks (` ``` ` / `~~~`) regardless
  of line width.
- Titles/headings (a line starting with `#`) are never wrapped and never
  flagged for length, regardless of width.
- HTML comments (`<!-- ... -->`) are detected as their own block (single- or
  multi-line) and passed through byte-for-byte, like code blocks.
- A line matched as containing a URL (`http://`, `https://`, `ftp://`, or
  `www.`) is emitted verbatim: it is never merged into paragraph reflow, so
  prose immediately before/after it still wraps normally on its own lines.
- Table detection requires a header row immediately followed by a valid
  separator row (`|---|`, with optional `:` alignment markers); anything
  else is treated as prose.
- This is a personal skill (`~/.claude/skills/md-format`) — it is not
  scoped to any one repo's workspace rules, but the caller invoking it is
  still responsible for its own repo's git/branch rules (this skill only
  rewrites file content, it never runs git).
- `markdownlint-cli` runs with the bundled `scripts/.markdownlint.jsonc`,
  which disables seven of its default rules and only they:
  - `MD013` (line-length) — has zero `--fix` support for line length in
    any mode (confirmed empirically), and its default URL-exemption
    semantics don't match rule 4 above (it only exempts a line with no
    whitespace past column 80, not any line merely containing a URL).
    Reflow detection and fixing both stay on this skill's own logic.
  - `MD034` (no-bare-urls) — its fix wraps bare URLs in `<...>`, which
    would violate rule 4's "emitted verbatim" guarantee.
  - `MD041` (first-line-h1) — this skill formats arbitrary markdown
    fragments, not only ones that open with a top-level heading.
  - `MD033` (no-inline-html) — not fixable, and flags every `<br>` in a
    table cell. Confluence-exported tables routinely use `<br>` for a
    cell line break; confirmed empirically against real synced docs in
    `md-files/` (`cache-improvements-eu.md`/`-us.md`).
  - `MD025` (single-h1) — not fixable, and flags any document with more
    than one top-level heading. Confluence-derived notebooks/incident
    docs commonly have several H1 sections by design; confirmed against
    `2026-09-02-platform-x-composition-api-incident-notebook.md`.
  - `MD040` (fenced-code-language) — not fixable, and flags every fenced
    code block with no language tag. Plain log/output paste blocks are
    normal and not this skill's concern; confirmed against the same
    incident notebook (~30 hits).
  - `MD036` (no-emphasis-as-heading) — *is* fixable, but its fix rewrites
    bold text into an actual heading, which is a structural/semantic
    edit, not formatting — it conflicts with this skill's own "no
    judgment calls" design. Confirmed against
    `cache-next-step-decision.md`, which deliberately uses
    `**Open questions**` as a bold label, not a heading.
  Everything else in markdownlint's default set stays on, including the
  table rules (`MD055`/`MD056`/`MD058`/`MD060`) — they don't conflict with
  `fix_table_block`, and `MD060` (configured `aligned`) is a useful
  detect-only double-check of the alignment this skill's own fixer
  applies (its own docs confirm the `aligned` style is never
  auto-fixable, only detectable). Don't re-enable any of the seven
  without re-deriving this reasoning first — each was confirmed
  empirically, most by running `--check-only` against this workspace's
  own real Confluence-synced markdown files (`md-files/*.md`), not just
  synthetic test input.
