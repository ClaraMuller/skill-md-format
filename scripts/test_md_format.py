#!/usr/bin/env python3
"""Unit tests for md_format.py. Run with: python3 -m pytest test_md_format.py
or: python3 test_md_format.py
"""

import shutil
import subprocess
import unittest
from unittest import mock

import md_format


class TestTextWidth(unittest.TestCase):
    def test_flags_long_line(self):
        long_line = "x" * 81 + "\n"
        violations = md_format.check([long_line])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].kind, "line-too-long")

    def test_accepts_short_line(self):
        line = ("x" * 80) + "\n"
        violations = md_format.check([line])
        self.assertEqual(violations, [])

    def test_fix_wraps_paragraph_to_80_columns(self):
        paragraph = [("word " * 40).strip() + "\n"]
        fixed = md_format.fix(paragraph)
        for line in fixed:
            self.assertLessEqual(len(line.rstrip("\n")), 80)
        self.assertEqual(len(md_format.check(fixed)), 0)

    def test_fix_preserves_list_marker_and_indent(self):
        paragraph = ["- " + ("word " * 40).strip() + "\n"]
        fixed = md_format.fix(paragraph)
        self.assertTrue(fixed[0].startswith("- "))
        self.assertTrue(all(len(l.rstrip("\n")) <= 80 for l in fixed))
        for line in fixed[1:]:
            self.assertTrue(line.startswith("  "))

    def test_fix_preserves_blockquote_marker_on_wrapped_lines(self):
        paragraph = ["> " + ("word " * 40).strip() + "\n"]
        fixed = md_format.fix(paragraph)
        self.assertTrue(all(l.startswith(">") for l in fixed))
        self.assertTrue(all(len(l.rstrip("\n")) <= 80 for l in fixed))
        self.assertGreater(len(fixed), 1)

    def test_headings_are_not_wrapped_even_if_long(self):
        heading = "# " + ("word " * 40).strip() + "\n"
        violations = md_format.check([heading])
        self.assertFalse(any(v.kind == "line-too-long" for v in violations))
        fixed = md_format.fix([heading])
        self.assertEqual(fixed, [heading])

    def test_code_block_is_untouched_regardless_of_width(self):
        block = [
            "```\n",
            "x" * 200 + "\n",
            "```\n",
        ]
        violations = md_format.check(block)
        self.assertEqual(violations, [])
        fixed = md_format.fix(block)
        self.assertEqual(fixed, block)


class TestUrlAndComments(unittest.TestCase):
    def test_long_line_with_url_is_not_flagged(self):
        line = "See https://example.com/" + ("a" * 80) + " for details.\n"
        self.assertGreater(len(line.rstrip("\n")), 80)
        violations = md_format.check([line])
        self.assertEqual(violations, [])

    def test_long_line_with_url_is_not_wrapped_or_broken(self):
        line = "See https://example.com/" + ("a" * 80) + " for details.\n"
        fixed = md_format.fix([line])
        self.assertEqual(fixed, [line])

    def test_url_inside_markdown_link_is_not_broken(self):
        line = (
            "Read the [docs](https://example.com/" + ("b" * 80) + ") first.\n"
        )
        fixed = md_format.fix([line])
        self.assertEqual(fixed, [line])
        self.assertEqual(md_format.check([line]), [])

    def test_single_line_comment_is_ignored(self):
        line = "<!-- " + ("x" * 100) + " -->\n"
        violations = md_format.check([line])
        self.assertEqual(violations, [])
        fixed = md_format.fix([line])
        self.assertEqual(fixed, [line])

    def test_block_comment_is_untouched(self):
        block = [
            "<!--\n",
            ("comment word " * 20).strip() + "\n",
            "-->\n",
        ]
        violations = md_format.check(block)
        self.assertEqual(violations, [])
        fixed = md_format.fix(block)
        self.assertEqual(fixed, block)

    def test_prose_around_comment_is_still_wrapped(self):
        lines = [
            ("word " * 40).strip() + "\n",
            "<!-- skip me " + ("y" * 100) + " -->\n",
            ("word " * 40).strip() + "\n",
        ]
        fixed = md_format.fix(lines)
        joined = "".join(fixed)
        self.assertIn("<!-- skip me " + ("y" * 100) + " -->\n", joined)
        wrapped_lines = [
            l for l in fixed if "<!--" not in l and "y" * 100 not in l
        ]
        self.assertTrue(all(len(l.rstrip("\n")) <= 80 for l in wrapped_lines))


class TestTable(unittest.TestCase):
    def test_flags_misaligned_table(self):
        table = [
            "| a | bbbb |\n",
            "|---|---|\n",
            "| ccc | d |\n",
        ]
        violations = md_format.check(table)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].kind, "table-not-aligned")

    def test_accepts_already_aligned_table(self):
        table = [
            "| a   | bbbb |\n",
            "| --- | ---- |\n",
            "| ccc | d    |\n",
        ]
        violations = md_format.check(table)
        self.assertEqual(violations, [])

    def test_fix_aligns_table_columns(self):
        table = [
            "| a | bbbb |\n",
            "|---|---|\n",
            "| ccc | d |\n",
        ]
        fixed = md_format.fix(table)
        self.assertEqual(len(md_format.check(fixed)), 0)
        widths = {len(line.rstrip("\n")) for line in fixed}
        self.assertEqual(len(widths), 1)

    def test_table_wide_column_not_flagged_for_80_col_rule(self):
        wide_cell = "x" * 100
        table = [
            f"| {wide_cell} |\n",
            "| " + "-" * 100 + " |\n",
            f"| {wide_cell} |\n",
        ]
        violations = md_format.check(table)
        self.assertEqual(violations, [])

    def test_fix_preserves_alignment_markers(self):
        table = [
            "| left | right | center |\n",
            "|:---|---:|:---:|\n",
            "| a | b | c |\n",
        ]
        fixed = md_format.fix(table)
        sep_line = fixed[1]
        self.assertIn(":-", sep_line.split("|")[1])
        self.assertIn("-:", sep_line.split("|")[2])
        self.assertTrue(
            sep_line.split("|")[3].strip().startswith(":")
            and sep_line.split("|")[3].strip().endswith(":")
        )

    def test_flags_table_not_followed_by_blank_line(self):
        lines = [
            "| a | b |\n",
            "| - | - |\n",
            "| c | d |\n",
            "Some prose right after, no blank line.\n",
        ]
        violations = md_format.check(lines)
        self.assertTrue(
            any(v.kind == "table-missing-blank-line-after" for v in violations)
        )

    def test_fix_inserts_blank_line_after_table(self):
        lines = [
            "| a | b |\n",
            "| - | - |\n",
            "| c | d |\n",
            "Some prose right after, no blank line.\n",
        ]
        fixed = md_format.fix(lines)
        table_end = next(
            i for i, l in enumerate(fixed) if l.strip() == "Some prose right after, no blank line."
        )
        self.assertEqual(fixed[table_end - 1], "\n")
        self.assertEqual(md_format.check(fixed), [])

    def test_table_already_followed_by_blank_line_is_not_flagged(self):
        lines = [
            "| a | b |\n",
            "| - | - |\n",
            "| c | d |\n",
            "\n",
            "Some prose after the table.\n",
        ]
        self.assertEqual(md_format.check(lines), [])

    def test_table_at_end_of_file_is_not_flagged(self):
        lines = [
            "| a | b |\n",
            "| - | - |\n",
            "| c | d |\n",
        ]
        self.assertEqual(md_format.check(lines), [])


class TestBlockSplitting(unittest.TestCase):
    def test_table_immediately_followed_by_text_is_separated(self):
        lines = [
            "| a | b |\n",
            "| - | - |\n",
            "| c | d |\n",
            "Some prose after the table.\n",
        ]
        blocks = md_format.split_blocks(lines)
        kinds = [k for k, _b, _s in blocks]
        self.assertIn("table", kinds)
        self.assertIn("text", kinds)


class TestRunMarkdownlint(unittest.TestCase):
    def test_missing_binary_reports_clear_error(self):
        with mock.patch.object(shutil, "which", return_value=None):
            ok, output = md_format.run_markdownlint("some.md", fix=True)
        self.assertFalse(ok)
        self.assertIn("markdownlint-cli not found on PATH", output)
        self.assertIn("npm install -g markdownlint-cli", output)

    def test_invokes_markdownlint_with_bundled_config_and_fix_flag(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with mock.patch.object(
            shutil, "which", return_value="/usr/local/bin/markdownlint"
        ), mock.patch.object(
            subprocess, "run", return_value=completed
        ) as run_mock:
            ok, output = md_format.run_markdownlint("some.md", fix=True)
        self.assertTrue(ok)
        self.assertEqual(output, "")
        called_cmd = run_mock.call_args.args[0]
        self.assertEqual(called_cmd[0], "markdownlint")
        self.assertIn("--config", called_cmd)
        config_index = called_cmd.index("--config") + 1
        self.assertEqual(
            called_cmd[config_index], str(md_format.MARKDOWNLINT_CONFIG)
        )
        self.assertIn("--fix", called_cmd)
        self.assertEqual(called_cmd[-1], "some.md")

    def test_check_only_omits_fix_flag(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="some.md:1 MD009 error\n", stderr=""
        )
        with mock.patch.object(
            shutil, "which", return_value="/usr/local/bin/markdownlint"
        ), mock.patch.object(subprocess, "run", return_value=completed):
            ok, output = md_format.run_markdownlint("some.md", fix=False)
        self.assertFalse(ok)
        self.assertIn("MD009", output)

    def test_remaining_violation_output_is_folded_in(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="some.md:2 MD060 error\n"
        )
        with mock.patch.object(
            shutil, "which", return_value="/usr/local/bin/markdownlint"
        ), mock.patch.object(subprocess, "run", return_value=completed):
            ok, output = md_format.run_markdownlint("some.md", fix=False)
        self.assertFalse(ok)
        self.assertIn("MD060", output)


@unittest.skipUnless(
    shutil.which("markdownlint"), "markdownlint-cli not installed"
)
class TestRunMarkdownlintIntegration(unittest.TestCase):
    def test_fix_resolves_trailing_whitespace_and_hard_tabs(self, tmp_path=None):
        import tempfile
        import os

        fd, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("# Heading   \n\nSome\ttext.\n")
            ok, _output = md_format.run_markdownlint(path, fix=True)
            with open(path) as f:
                contents = f.read()
            self.assertNotIn("   \n", contents)
            self.assertNotIn("\t", contents)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
