"""Tests for fontaine's deterministic bundle build.

The bundle artifacts (fonts.zip, fonts.json, manifest.json) are cache
keys for FontLoader: an unchanged font set must produce identical
artifact bytes and an identical version, so clients reuse their cache
instead of re-downloading on every rebuild.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
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


class FullOutputDeterminismTest(unittest.TestCase):
    """fonts.json and manifest.json bytes must not vary between builds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def sample_fonts(self):
        return [
            {
                "id": "01-demo",
                "name": "Demo Font",
                "dir_name": "01-demo",
                "category": build_bundle.get_tags(1, "Demo Font", "serif")[1],
                "style": "serif",
                "tags": build_bundle.get_tags(1, "Demo Font", "serif"),
                "license": "OFL-1.1",
                "files": [
                    {"filename": "regular.woff2", "size": 4, "sha256": "aa" * 32},
                    {"filename": "italic.woff2", "size": 4, "sha256": "bb" * 32},
                ],
            },
            {
                "id": "02-quirky",
                "name": "Quirky Condensed",
                "dir_name": "02-quirky",
                "category": build_bundle.get_tags(52, "Quirky Condensed", "display")[1],
                "style": "display",
                "tags": build_bundle.get_tags(52, "Quirky Condensed", "display"),
                "license": "MIT",
                "files": [{"filename": "regular.woff2", "size": 7, "sha256": "cc" * 32}],
            },
        ]

    def test_repeated_assembly_produces_identical_artifact_bytes(self):
        fonts = self.sample_fonts()
        first = build_bundle.build_catalog_and_manifest(fonts, 1234, "hash-one")
        second = build_bundle.build_catalog_and_manifest(fonts, 1234, "hash-one")

        self.assertEqual(json.dumps(first[0], indent=2), json.dumps(second[0], indent=2))
        self.assertEqual(json.dumps(first[1], indent=2), json.dumps(second[1], indent=2))

    def test_version_date_is_deterministic_and_compatible(self):
        # version_date stays in the metadata contract (FontLoader persists
        # manifest.version_date) but must not track the build clock.
        catalog, manifest = build_bundle.build_catalog_and_manifest(
            self.sample_fonts(), 1234, "hash-one")
        self.assertEqual(catalog["version_date"], manifest["version_date"])
        # Reproducible-builds default: Unix epoch when SOURCE_DATE_EPOCH
        # is unset, so the value is identical on every machine.
        self.assertEqual(manifest["version_date"],
                         build_bundle.bundle_version_date(0))
        self.assertEqual(build_bundle.bundle_version_date(0),
                         "1970-01-01T00:00:00+00:00")

    def test_source_date_epoch_overrides_version_date(self):
        date = build_bundle.bundle_version_date(1600000000)
        self.assertEqual(date, "2020-09-13T12:26:40+00:00")
        catalog, manifest = build_bundle.build_catalog_and_manifest(
            self.sample_fonts(), 1234, "hash-one", version_date=date)
        self.assertEqual(catalog["version_date"], date)
        self.assertEqual(manifest["version_date"], date)

    def test_full_outputs_identical_across_python_processes(self):
        # End-to-end: zip + catalog + manifest assembled in two separate
        # interpreter processes with different hash seeds (string hashing
        # is randomized per process) must yield identical artifact bytes.
        snippet = textwrap.dedent("""
            import json, pathlib, sys
            sys.path.insert(0, %r)
            import build_bundle
            fonts = json.loads(sys.argv[1])
            zip_path, size, sha = build_bundle.create_zip_bundle(
                fonts, pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
            catalog, manifest = build_bundle.build_catalog_and_manifest(
                fonts, size, sha)
            print(json.dumps({"catalog": catalog, "manifest": manifest,
                              "sha256": sha}))
        """) % str(Path(build_bundle.__file__).resolve().parent)

        fonts = self.sample_fonts()
        outputs = []
        for i, seed in enumerate(("1", "7")):
            tree = self.base / f"build-{i}"
            for font in fonts:
                for file_info in font["files"]:
                    target = tree / font["dir_name"] / file_info["filename"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"font-" + font["id"].encode())
            env = dict(os.environ, PYTHONHASHSEED=seed)
            result = subprocess.run(
                [sys.executable, "-c", snippet, json.dumps(fonts), str(tree),
                 str(self.base / f"fonts-{i}.zip")],
                capture_output=True, text=True, env=env, check=True)
            outputs.append(json.loads(result.stdout.strip().splitlines()[-1]))

        self.assertEqual(outputs[0]["catalog"], outputs[1]["catalog"])
        self.assertEqual(outputs[0]["manifest"], outputs[1]["manifest"])
        self.assertEqual(outputs[0]["sha256"], outputs[1]["sha256"])


if __name__ == "__main__":
    unittest.main()