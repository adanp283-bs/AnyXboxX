"""Run the actual workflow shell against local repositories; no GitHub writes."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


PROJECT = Path(__file__).resolve().parents[1]
REAL_GIT = shutil.which("git")
WORKFLOW = yaml.safe_load((PROJECT / ".github/workflows/sync-anyxboxx.yml").read_text())
SCRIPT = WORKFLOW["jobs"]["sync"]["steps"][0]["run"]


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="anyxboxx-sync-test-", dir=PROJECT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream.git"
        self.fork = self.root / "fork.git"
        self.work = self.root / "work"
        self.runner = self.root / "runner"
        self.runner.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.summary = self.root / "summary"
        self.summary.touch()
        config = self.root / "gitconfig"
        config.write_text(
            '[user]\n  name = Sync Test\n  email = sync-test@example.invalid\n'
            f'[url "{self.upstream.as_uri()}"]\n'
            '  insteadOf = https://github.com/LooperSalty/AnyXboxX.git\n'
            f'[url "{self.fork.as_uri()}"]\n'
            '  insteadOf = git@github.com:adanp283-bs/AnyXboxX.git\n'
        )
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM="1")
        for repo in (self.upstream, self.fork):
            self.git("init", "-q", "--bare", "--initial-branch=main", str(repo))
        self.git("init", "-q", "--initial-branch=main", str(self.work))
        self.base = self.commit("README.md", "base\n", "Base")
        self.git("-C", str(self.work), "push", "-q", str(self.upstream), "HEAD:main")
        self.git("-C", str(self.work), "push", "-q", str(self.fork), "HEAD:legacy-code", "HEAD:sync-control", "HEAD:main")
        self.target = self.commit(".github/workflows/runtime.yml", "name: Upstream\n", "Update upstream workflow")
        self.git("-C", str(self.work), "push", "-q", str(self.upstream), "HEAD:main")

        gh = self.bin / "gh"
        gh.write_text(
            "#!/usr/bin/env python3\n"
            "import os, subprocess, sys\n"
            "path = sys.argv[2]\n"
            "if path == 'repos/LooperSalty/AnyXboxX':\n"
            "    print(os.environ.get('TEST_UPSTREAM_ID', '1466028817'))\n"
            "elif path == 'meta':\n"
            "    print('github.com ssh-ed25519 TEST_ONLY_NOT_USED_FOR_SSH')\n"
            "elif path.endswith('/git/ref/heads/main'):\n"
            "    repo = os.environ['TEST_UPSTREAM']\n"
            f"    subprocess.run([{REAL_GIT!r}, '--git-dir=' + repo, 'rev-parse', 'refs/heads/main'], check=True)\n"
            "elif path == 'repos/adanp283-bs/AnyXboxX/git/matching-refs/heads/main':\n"
            "    if os.environ.get('TEST_REF_API_ERROR'):\n"
            "        raise SystemExit('Branch lookup failed')\n"
            f"    result = subprocess.run([{REAL_GIT!r}, '--git-dir=' + os.environ['TEST_FORK'], 'rev-parse', '--verify', 'refs/heads/main'], text=True, capture_output=True)\n"
            "    if result.returncode == 0:\n"
            "        print(result.stdout.strip())\n"
            "else:\n"
            "    raise SystemExit('Unexpected API request: ' + path)\n"
        )
        gh.chmod(0o755)
        git_wrapper = self.bin / "git"
        git_wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import os, subprocess, sys\n"
            "if sys.argv[1:3] == ['push', 'origin'] and os.environ.get('TEST_RACE_SHA'):\n"
            f"    subprocess.run([{REAL_GIT!r}, '--git-dir=' + os.environ['TEST_RACE_REPO'], 'update-ref', os.environ.get('TEST_RACE_REF', 'refs/heads/main'), os.environ['TEST_RACE_SHA']], check=True)\n"
            f"os.execv({REAL_GIT!r}, [{REAL_GIT!r}] + sys.argv[1:])\n"
        )
        git_wrapper.chmod(0o755)
        self.env.update(
            PATH=str(self.bin) + os.pathsep + self.env["PATH"],
            TEST_UPSTREAM=str(self.upstream),
            TEST_FORK=str(self.fork),
            GITHUB_REPOSITORY="adanp283-bs/AnyXboxX",
            GITHUB_REF="refs/heads/sync-control",
            RUNNER_TEMP=str(self.runner),
            GITHUB_STEP_SUMMARY=str(self.summary),
            GH_TOKEN="test-only",
            ANYXBOXX_SYNC_KEY="test-only-no-real-key",
        )

    def git(self, *args):
        return subprocess.run([REAL_GIT, *args], env=self.env, text=True, capture_output=True, check=True).stdout.strip()

    def commit(self, filename, content, message):
        path = self.work / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git("-C", str(self.work), "add", filename)
        self.git("-C", str(self.work), "commit", "-qm", message)
        return self.git("-C", str(self.work), "rev-parse", "HEAD")

    def fork_sha(self):
        return self.git("--git-dir=" + str(self.fork), "rev-parse", "refs/heads/main")

    def run_sync(self, **overrides):
        result = subprocess.run(["bash", "-c", SCRIPT], cwd=self.root, env=dict(self.env, **overrides), text=True, capture_output=True, timeout=30)
        self.assertEqual(list(self.runner.iterdir()), [], "Temporary key directory must be removed")
        self.assertEqual(self.git("--git-dir=" + str(self.fork), "rev-parse", "refs/heads/sync-control"), self.base)
        self.assertEqual(self.git("--git-dir=" + str(self.fork), "rev-parse", "refs/heads/legacy-code"), self.base)
        self.assertNotIn("test-only-no-real-key", result.stdout + result.stderr)
        return result

    def independent_commit(self):
        self.git("-C", str(self.work), "switch", "-qc", "independent", self.base)
        sha = self.commit("local.txt", "keep this\n", "Independent fork change")
        self.git("-C", str(self.work), "push", "-q", str(self.fork), "HEAD:race-candidate")
        return sha

    def test_fast_forward_includes_workflow_files(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.fork_sha(), self.target)
        self.assertIn(self.target, self.summary.read_text())
        self.assertEqual(self.git("--git-dir=" + str(self.fork), "show", "main:.github/workflows/runtime.yml"), "name: Upstream")

    def test_initial_import_keeps_other_branches(self):
        self.git("--git-dir=" + str(self.fork), "update-ref", "-d", "refs/heads/main")
        self.git("-C", str(self.work), "switch", "--orphan", "new-project")
        unrelated = self.commit("ANYXBOXX.md", "new project\n", "AnyXboxX root")
        self.git("-C", str(self.work), "push", "-q", str(self.upstream), "HEAD:import-candidate")
        self.git("--git-dir=" + str(self.upstream), "update-ref", "refs/heads/main", unrelated)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.fork_sha(), unrelated)
        self.assertIn("(new branch)", self.summary.read_text())

    def test_up_to_date(self):
        self.git("-C", str(self.work), "push", "-q", str(self.fork), "HEAD:main")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up to date", self.summary.read_text())
        self.assertEqual(self.fork_sha(), self.target)

    def test_missing_key_fails_before_sync(self):
        result = self.run_sync(ANYXBOXX_SYNC_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Configure the protected anyxboxx-sync environment", result.stderr)
        self.assertEqual(self.fork_sha(), self.base)

    def test_wrong_source_id_fails_before_sync(self):
        result = self.run_sync(TEST_UPSTREAM_ID="123")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected upstream", result.stderr)
        self.assertEqual(self.fork_sha(), self.base)

    def test_branch_lookup_error_does_not_create_or_change_branch(self):
        result = self.run_sync(TEST_REF_API_ERROR="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fork_sha(), self.base)

    def test_diverged_fork_is_preserved(self):
        independent = self.independent_commit()
        self.git("--git-dir=" + str(self.fork), "update-ref", "refs/heads/main", independent)
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)
        self.assertEqual(self.fork_sha(), independent)

    def test_concurrent_fork_change_is_preserved(self):
        independent = self.independent_commit()
        result = self.run_sync(TEST_RACE_REPO=str(self.fork), TEST_RACE_SHA=independent)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fork_sha(), independent)

    def test_upstream_advances_after_fetch(self):
        later = self.commit("next.txt", "later upstream commit\n", "Next upstream update")
        self.git("-C", str(self.work), "push", "-q", str(self.upstream), "HEAD:main")
        self.git("--git-dir=" + str(self.upstream), "update-ref", "refs/heads/main", self.target)
        result = self.run_sync(TEST_RACE_REPO=str(self.upstream), TEST_RACE_SHA=later, TEST_RACE_REF="refs/heads/main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.fork_sha(), self.target)
        self.assertEqual(self.git("--git-dir=" + str(self.upstream), "rev-parse", "main"), later)
        self.assertIn(self.target, self.summary.read_text())


if __name__ == "__main__":
    unittest.main()
