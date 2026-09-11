#!/usr/bin/env python3
"""Smallest real check for homepage-integrate.py's merge logic. Run directly:
    python3 test_homepage_integrate.py
"""

import tempfile
import unittest
from pathlib import Path

import yaml

from homepage_integrate import GROUP_NAME, merge_tile


class MergeTileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "services.yaml"
        self.path.write_text(
            yaml.safe_dump(
                [
                    {"Media": [{"Jellyfin": {"href": "http://x:8096"}}]},
                    {"Guides": [{"Walkthrough": {"href": "http://x/docs"}}]},
                ]
            )
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_inserts_before_guides_and_leaves_other_groups_alone(self):
        merge_tile(self.path, "http://host:3000/nightwire")
        groups = yaml.safe_load(self.path.read_text())
        names = [next(iter(g)) for g in groups]
        self.assertEqual(names, ["Media", GROUP_NAME, "Guides"])

    def test_rerun_replaces_rather_than_duplicates(self):
        merge_tile(self.path, "http://host:3000/nightwire")
        merge_tile(self.path, "http://host:9999/nightwire")
        groups = yaml.safe_load(self.path.read_text())
        matches = [g for g in groups if GROUP_NAME in g]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][GROUP_NAME][0][GROUP_NAME]["href"], "http://host:9999/nightwire")


if __name__ == "__main__":
    unittest.main()
