#!/usr/bin/env python3
"""Unit tests for md_format.py. Run with: python3 -m pytest test_md_format.py
or: python3 test_md_format.py
"""

import unittest

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

    def test_heading_number_comma_is_still_flagged_and_fixed(self):
        heading = "# Q1 2026: 10,000 users\n"
        violations = md_format.check([heading])
        self.assertTrue(
            any(v.kind == "number-comma-separator" for v in violations)
        )
        fixed = md_format.fix([heading])
        self.assertIn("10000", fixed[0])
        self.assertNotIn(",", fixed[0])

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


class TestNumberCommaSeparator(unittest.TestCase):
    def test_flags_comma_separated_number_in_prose(self):
        violations = md_format.check(["We served 10,000 requests today.\n"])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].kind, "number-comma-separator")

    def test_accepts_number_without_comma(self):
        violations = md_format.check(["We served 10000 requests today.\n"])
        self.assertEqual(violations, [])

    def test_fix_strips_comma_from_number(self):
        fixed = md_format.fix(["We served 10,000 requests today.\n"])
        self.assertIn("10000", fixed[0])
        self.assertNotIn(",", fixed[0])
        self.assertEqual(md_format.check(fixed), [])

    def test_fix_strips_comma_in_multi_group_number(self):
        fixed = md_format.fix(["Total: 1,234,567 users.\n"])
        self.assertIn("1234567", fixed[0])

    def test_fix_strips_comma_in_list_item(self):
        fixed = md_format.fix(["- cost is 12,000 dollars per month\n"])
        self.assertTrue(fixed[0].startswith("-"))
        self.assertIn("12000", fixed[0])
        self.assertNotIn(",", fixed[0])

    def test_fix_strips_comma_in_table_cell(self):
        table = [
            "| Metric | Value |\n",
            "| --- | --- |\n",
            "| Requests | 10,000 |\n",
        ]
        fixed = md_format.fix(table)
        joined = "".join(fixed)
        self.assertIn("10000", joined)
        self.assertNotIn(",", joined)
        self.assertEqual(md_format.check(fixed), [])

    def test_number_comma_in_url_line_is_left_untouched(self):
        line = "See https://example.com/report?count=10,000 for details.\n"
        fixed = md_format.fix([line])
        self.assertEqual(fixed, [line])
        self.assertEqual(md_format.check([line]), [])

    def test_does_not_touch_list_separated_by_commas(self):
        line = "Options are a, b, and c.\n"
        fixed = md_format.fix([line])
        self.assertEqual(fixed[0].strip(), line.strip())
        self.assertEqual(md_format.check([line]), [])


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


if __name__ == "__main__":
    unittest.main()
