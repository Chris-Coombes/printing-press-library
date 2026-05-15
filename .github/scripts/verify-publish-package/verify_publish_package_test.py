#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import verify_publish_package as verifier


class PublishPackageVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="verify-publish-package-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp))
        self.old_root = verifier.REPO_ROOT
        verifier.REPO_ROOT = self.tmp
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("commit", "--allow-empty", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "-c", "feature")

    def tearDown(self) -> None:
        verifier.REPO_ROOT = self.old_root

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.tmp,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write(self, rel: str, content: str = "") -> None:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def write_valid_cli(self) -> Path:
        cli_dir = self.tmp / "library" / "cloud" / "example"
        manifest = {
            "schema_version": 1,
            "api_name": "example",
            "category": "cloud",
            "cli_name": "example-pp-cli",
            "printer": "tmchow",
            "printing_press_version": "4.0.1",
            "run_id": "20260509T010203Z-test",
            "mcp_binary": "example-pp-mcp",
            "mcp_tool_count": 1,
            "novel_features": [
                {
                    "name": "Example search",
                    "command": "search",
                    "description": "Searches example data.",
                }
            ],
        }
        patch_manifest = {"schema_version": 1, "applied_at": "2026-05-09", "patches": []}
        files = {
            ".printing-press.json": json.dumps(manifest),
            ".printing-press-patches.json": json.dumps(patch_manifest),
            "AGENTS.md": "# Agents\n",
            "README.md": "# Example\n",
            "SKILL.md": "---\nname: pp-example\n---\n",
            "go.mod": "module github.com/mvanhorn/printing-press-library/library/cloud/example\n",
            ".goreleaser.yaml": "version: 2\n",
            "LICENSE": "MIT\n",
            "NOTICE": "Example\n",
            "manifest.json": "{}\n",
            "tools-manifest.json": "{}\n",
            "cmd/example-pp-cli/main.go": "package main\n",
            "cmd/example-pp-mcp/main.go": "package main\n",
            ".manuscripts/20260509T010203Z-test/research/research.json": "{}\n",
            ".manuscripts/20260509T010203Z-test/proofs/shipcheck.json": "{}\n",
        }
        for name, content in files.items():
            self.write(f"library/cloud/example/{name}", content)
        return cli_dir

    def test_new_cli_missing_publish_artifacts_fails(self) -> None:
        self.write("library/cloud/bad/.printing-press.json", '{"api_name": "bad", "cli_name": "bad-pp-cli"}')
        self.write("library/cloud/bad/go.mod", "module github.com/mvanhorn/printing-press-library/library/cloud/bad\n")

        cli_dir = self.tmp / "library" / "cloud" / "bad"
        problems = verifier.validate_cli_dir(cli_dir, strict=True)
        messages = [p.message for p in problems]

        self.assertTrue(any("AGENTS.md" in msg for msg in messages))
        self.assertTrue(any(".printing-press-patches.json" in msg for msg in messages))
        self.assertTrue(any("run_id" in msg for msg in messages))

    def test_valid_new_cli_and_pr_body_has_no_suggestions(self) -> None:
        self.write_valid_cli()
        self.git("add", ".")
        self.git("commit", "-m", "add example")

        touched = verifier.changed_cli_dirs(self.base)
        new_dirs = [d for d in touched if verifier.is_new_cli(self.base, d)]
        body = "### Publication Path\nnew print\n\n### Novel Commands\n- search\n"
        problems = []
        for cli_dir in touched:
            problems.extend(verifier.validate_cli_dir(cli_dir, strict=cli_dir in new_dirs))
        suggestions = verifier.pr_body_suggestions(body, new_dirs)

        self.assertEqual([], problems)
        self.assertEqual([], suggestions)

    def test_missing_pr_body_sections_are_advisory_for_new_cli(self) -> None:
        self.write_valid_cli()
        self.git("add", ".")
        self.git("commit", "-m", "add example")

        touched = verifier.changed_cli_dirs(self.base)
        new_dirs = [d for d in touched if verifier.is_new_cli(self.base, d)]
        suggestions = verifier.pr_body_suggestions("", new_dirs)

        self.assertEqual(1, len(suggestions))
        self.assertIn("### Novel Commands", suggestions[0])
        self.assertIn("### Publication Path", suggestions[0])
        self.assertIn("| `search` | Example search | Searches example data. |", suggestions[0])

    def test_new_cli_directory_with_pp_cli_suffix_fails(self) -> None:
        cli_dir = self.tmp / "library" / "cloud" / "example-pp-cli"
        manifest = {
            "schema_version": 1,
            "api_name": "example-pp-cli",
            "category": "cloud",
            "cli_name": "example-pp-cli",
            "printer": "tmchow",
            "printing_press_version": "4.0.1",
            "run_id": "20260509T010203Z-test",
            "novel_features": [{"name": "n", "command": "search", "description": "d"}],
        }
        files = {
            ".printing-press.json": json.dumps(manifest),
            ".printing-press-patches.json": json.dumps({"schema_version": 1, "applied_at": "2026-05-09", "patches": []}),
            "AGENTS.md": "# Agents\n",
            "README.md": "# Example\n",
            "SKILL.md": "---\nname: pp-example\n---\n",
            "go.mod": "module github.com/mvanhorn/printing-press-library/library/cloud/example-pp-cli\n",
            ".goreleaser.yaml": "version: 2\n",
            "LICENSE": "MIT\n",
            "NOTICE": "Example\n",
            "cmd/example-pp-cli/main.go": "package main\n",
            ".manuscripts/20260509T010203Z-test/research/research.json": "{}\n",
            ".manuscripts/20260509T010203Z-test/proofs/shipcheck.json": "{}\n",
        }
        for name, content in files.items():
            self.write(f"library/cloud/example-pp-cli/{name}", content)

        problems = verifier.validate_cli_dir(cli_dir, strict=True)
        messages = [p.message for p in problems]

        self.assertTrue(any("-pp-cli/-pp-mcp binary suffix" in msg for msg in messages))

    def test_existing_cli_with_pp_cli_suffix_does_not_fail_when_non_strict(self) -> None:
        cli_dir = self.tmp / "library" / "cloud" / "legacy-pp-cli"
        manifest = {
            "schema_version": 1,
            "api_name": "legacy-pp-cli",
            "category": "cloud",
            "cli_name": "legacy-pp-cli",
        }
        self.write("library/cloud/legacy-pp-cli/.printing-press.json", json.dumps(manifest))
        self.write("library/cloud/legacy-pp-cli/cmd/legacy-pp-cli/main.go", "package main\n")

        problems = verifier.validate_cli_dir(cli_dir, strict=False)
        messages = [p.message for p in problems]

        self.assertFalse(any("-pp-cli/-pp-mcp binary suffix" in msg for msg in messages))


class ValidatePatchManifestTest(unittest.TestCase):
    """Validate that .printing-press-patches.json structural checks still
    fire (every patches[] entry must be an object with a non-empty
    `files` list referencing files that exist). The previous
    `// PATCH` source-marker requirement was removed — the manifest
    itself is the audit record; an in-source marker was redundant.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="validate-patch-manifest-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp))

    def _cli_dir(self, name: str) -> Path:
        cli = self.tmp / name
        cli.mkdir()
        return cli

    def test_passes_when_files_exist_regardless_of_markers(self) -> None:
        # The PATCH-marker check is gone: a patches[] entry with valid
        # files that exist passes even when no file carries any `// PATCH`
        # comment. The manifest entry is itself the audit record.
        cli = self._cli_dir("no-markers")
        (cli / "foo.go").write_text("package foo\n// no marker here\n")
        (cli / "spec.json").write_text('{"x": 1}\n')
        (cli / ".printing-press-patches.json").write_text(
            '{"patches": [{"id": "mixed", "files": ["foo.go", "spec.json"]}]}\n'
        )
        problems = verifier.validate_patch_manifest(cli)
        self.assertEqual(problems, [])

    def test_fails_when_referenced_file_missing(self) -> None:
        # Structural check still applies: referenced files must exist.
        cli = self._cli_dir("missing-file")
        (cli / ".printing-press-patches.json").write_text(
            '{"patches": [{"id": "vanished", "files": ["nope.go"]}]}\n'
        )
        problems = verifier.validate_patch_manifest(cli)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not exist", problems[0].message)

    def test_fails_on_empty_files_list(self) -> None:
        cli = self._cli_dir("empty-files")
        (cli / ".printing-press-patches.json").write_text(
            '{"patches": [{"id": "empty", "files": []}]}\n'
        )
        problems = verifier.validate_patch_manifest(cli)
        self.assertEqual(len(problems), 1)
        self.assertIn("must list one or more files", problems[0].message)



if __name__ == "__main__":
    unittest.main()
