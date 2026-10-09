"""Tests for fontaine's deterministic bundle build.

The bundle artifacts (fonts.zip, fonts.json, manifest.json) are cache
keys for FontLoader: an unchanged font set must produce identical
artifact bytes and an identical version, so clients reuse their cache
instead of re-downloading on every rebuild.
"""

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_bundle


def make_font_dir(root: Path, dir_name: str, files: dict) -> Path:
    """Create a font directory with the given {filename: bytes} content."""
    font_dir = root / dir_name
    font_dir.mkdir(parents=True)
    for name, content in files.items():
        target = font_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return font_dir


def catalog_for(dir_name: str, filenames: list) -> list:
    """Minimal catalog entry list as consumed by create_zip_bundle."""
    return [{
        "dir_name": dir_name,
        "files": [{"filename": name} for name in filenames],
    }]


class ZipDeterminismTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_identical_content_with_different_mtimes_makes_identical_zip(self):
        content = {"a.woff2": b"font-bytes-a", "sub/b.woff2": b"font-bytes-b"}
        fonts = catalog_for("01-demo", ["a.woff2", "sub/b.woff2"])

        tree_one = make_font_dir(self.base / "one", "01-demo", content)
        tree_two = make_font_dir(self.base / "two", "01-demo", content)
        # Simulate a fresh download: different timestamps on identical bytes.
        for f in tree_two.rglob("*"):
            f.stat()  # ensure exists
        import os
        os.utime(tree_two / "a.woff2", (1600000000, 1600000000))
        os.utime(tree_two / "sub" / "b.woff2", (1700000000, 1700000000))

        zip_one, _, hash_one = build_bundle.create_zip_bundle(
            fonts, tree_one.parent, self.base / "one.zip")
        zip_two, _, hash_two = build_bundle.create_zip_bundle(
            fonts, tree_two.parent, self.base / "two.zip")

        self.assertEqual(zip_one.read_bytes(), zip_two.read_bytes())
        self.assertEqual(hash_one, hash_two)

    def test_changed_font_bytes_change_the_zip_and_hash(self):
        fonts = catalog_for("01-demo", ["a.woff2"])
        tree_one = make_font_dir(self.base / "one", "01-demo", {"a.woff2": b"version-one"})
        tree_two = make_font_dir(self.base / "two", "01-demo", {"a.woff2": b"version-two"})

        _, _, hash_one = build_bundle.create_zip_bundle(
            fonts, tree_one.parent, self.base / "one.zip")
        _, _, hash_two = build_bundle.create_zip_bundle(
            fonts, tree_two.parent, self.base / "two.zip")

        self.assertNotEqual(hash_one, hash_two)

    def test_zip_entries_are_sorted_with_fixed_metadata(self):
        # Deliberately unsorted catalog order.
        fonts = catalog_for("01-demo", ["z.woff2", "a.woff2", "m.woff2"])
        make_font_dir(self.base / "one", "01-demo",
                      {name: b"data-" + name.encode() for name in ["z.woff2", "a.woff2", "m.woff2"]})

        zip_path, _, _ = build_bundle.create_zip_bundle(
            fonts, self.base / "one", self.base / "out.zip")

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            self.assertEqual(names, sorted(names))
            for info in zf.infolist():
                self.assertEqual(info.date_time, build_bundle.ZIP_EPOCH)

    def test_missing_font_files_are_skipped(self):
        fonts = catalog_for("01-demo", ["present.woff2", "absent.woff2"])
        make_font_dir(self.base / "one", "01-demo", {"present.woff2": b"data"})

        zip_path, _, _ = build_bundle.create_zip_bundle(
            fonts, self.base / "one", self.base / "out.zip")

        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(zf.namelist(), ["01-demo/present.woff2"])


class BundleVersionTest(unittest.TestCase):
    def test_version_is_stable_for_identical_content(self):
        fonts = catalog_for("01-demo", ["a.woff2"])
        first = build_bundle.derive_bundle_version(fonts, "abc123")
        second = build_bundle.derive_bundle_version(json.loads(json.dumps(fonts)), "abc123")
        self.assertEqual(first, second)

    def test_version_changes_when_content_changes(self):
        fonts = catalog_for("01-demo", ["a.woff2"])
        self.assertNotEqual(
            build_bundle.derive_bundle_version(fonts, "sha-one"),
            build_bundle.derive_bundle_version(fonts, "sha-two"))
        self.assertNotEqual(
            build_bundle.derive_bundle_version(fonts, "same-sha"),
            build_bundle.derive_bundle_version(
                catalog_for("02-other", ["a.woff2"]), "same-sha"))

    def test_version_fits_js_safe_integer_range(self):
        # FontLoader compares versions as JavaScript Numbers; the derived
        # version must stay exact below 2**53.
        fonts = catalog_for("01-demo", ["a.woff2"])
        version = build_bundle.derive_bundle_version(fonts, "abc")
        self.assertGreaterEqual(version, 0)
        self.assertLess(version, 2 ** 53)


class CatalogDeterminismTest(unittest.TestCase):
    def test_tags_are_deterministically_ordered(self):
        # Same inputs must always produce the same tag order; previously
        # set() iteration order varied between Python processes.
        expected = ["quirky", "display", "variable", "condensed"]
        self.assertEqual(build_bundle.get_tags(51, "Demo Variable Condensed", "display"), expected)
        self.assertEqual(build_bundle.get_tags(51, "Demo Variable Condensed", "display"), expected)

    def test_tags_are_deduplicated(self):
        # A font numbered 51 whose style is "quirky" would duplicate the
        # tag under the old set()-based dedupe contract; it must appear once.
        tags = build_bundle.get_tags(51, "Demo", "quirky")
        self.assertEqual(tags.count("quirky"), 1)


if __name__ == "__main__":
    unittest.main()