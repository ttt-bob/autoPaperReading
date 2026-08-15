import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RunDailyExportStepTest(unittest.TestCase):
    def test_auto_mode_does_not_resume_stale_done_state(self):
        state_file = ROOT / ".run_state"
        done_file = ROOT / ".daily_done"
        previous_state = state_file.read_text(encoding="utf-8") if state_file.exists() else None
        previous_done = done_file.read_text(encoding="utf-8") if done_file.exists() else None

        try:
            state_file.write_text("20260702_100637|done|2026-07-02 10:06:37\n", encoding="utf-8")
            done_file.write_text("2026-07-08\n", encoding="utf-8")

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                fake_bin = tmp_path / "bin"
                fake_bin.mkdir()
                clashctl_dir = tmp_path / "clashctl" / "scripts" / "cmd"
                clashctl_dir.mkdir(parents=True)
                uv_log = tmp_path / "uv.log"
                git_log = tmp_path / "git.log"

                (fake_bin / "uv").write_text(
                    textwrap.dedent(
                        """\
                        #!/usr/bin/env bash
                        echo "uv $*" >> "$UV_LOG"
                        exit 0
                        """
                    ),
                    encoding="utf-8",
                )
                (fake_bin / "git").write_text(
                    textwrap.dedent(
                        """\
                        #!/usr/bin/env bash
                        echo "git $*" >> "$GIT_LOG"
                        exit 0
                        """
                    ),
                    encoding="utf-8",
                )
                (clashctl_dir / "clashctl.sh").write_text(
                    textwrap.dedent(
                        """\
                        clashctl() {
                            echo "clashctl $*" >> "$CLASH_LOG"
                        }
                        """
                    ),
                    encoding="utf-8",
                )
                (fake_bin / "nc").write_text(
                    "#!/usr/bin/env bash\nexit 0\n",
                    encoding="utf-8",
                )
                os.chmod(fake_bin / "uv", 0o755)
                os.chmod(fake_bin / "git", 0o755)
                os.chmod(fake_bin / "nc", 0o755)

                env = os.environ.copy()
                env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
                env["UV_LOG"] = str(uv_log)
                env["GIT_LOG"] = str(git_log)
                env["CLASH_LOG"] = str(tmp_path / "clash.log")
                env["CLASHCTL_HOME"] = str(tmp_path / "clashctl")
                env["PUBLIC_SYNC_ENABLED"] = "0"

                result = subprocess.run(
                    ["bash", str(ROOT / "run_daily.sh"), "--auto"],
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                uv_lines = uv_log.read_text(encoding="utf-8")
                self.assertIn("uv run python jobs/daily_ingest.py", uv_lines)
                self.assertEqual((tmp_path / "clash.log").read_text(encoding="utf-8"), "clashctl on\n")
                self.assertNotIn("已完成，跳过", result.stdout)
                self.assertFalse(state_file.exists())
        finally:
            if previous_state is None:
                state_file.unlink(missing_ok=True)
            else:
                state_file.write_text(previous_state, encoding="utf-8")
            if previous_done is None:
                done_file.unlink(missing_ok=True)
            else:
                done_file.write_text(previous_done, encoding="utf-8")

    def test_optional_obsidian_export_failure_does_not_fail_export_step(self):
        result, state_text = self._run_step_export(papers_status=0, obsidian_status=7)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(state_text)
        self.assertIn("|export|", state_text)

    def test_primary_papers_export_failure_fails_export_step(self):
        result, state_text = self._run_step_export(papers_status=5, obsidian_status=0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(state_text)

    def test_url_gui_mode_runs_single_ingest_without_state_file(self):
        previous_state = (ROOT / ".run_state").read_text(encoding="utf-8") if (ROOT / ".run_state").exists() else None

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            uv_log = tmp_path / "uv.log"
            git_log = tmp_path / "git.log"

            (fake_bin / "uv").write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    echo "uv $*" >> "$UV_LOG"
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            (fake_bin / "git").write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    echo "git $*" >> "$GIT_LOG"
                    if [[ "$1 $2 $3" == "diff --cached --quiet" ]]; then
                        exit 1
                    fi
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            os.chmod(fake_bin / "uv", 0o755)
            os.chmod(fake_bin / "git", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["UV_LOG"] = str(uv_log)
            env["GIT_LOG"] = str(git_log)
            env["PUBLIC_SYNC_ENABLED"] = "0"

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "run_daily.sh"),
                    "--url",
                    "https://arxiv.org/abs/2509.18119",
                    "--gui",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            uv_lines = uv_log.read_text(encoding="utf-8")
            self.assertIn(
                "uv run python jobs/ingest_url.py https://arxiv.org/abs/2509.18119 --save-category gui",
                uv_lines,
            )
            self.assertIn("uv run python jobs/export_papers.py --cloud", uv_lines)
            self.assertIn("uv run python jobs/export_gui_taxonomy.py", uv_lines)
            self.assertIn("git push origin master", git_log.read_text(encoding="utf-8"))

        current_state = (ROOT / ".run_state").read_text(encoding="utf-8") if (ROOT / ".run_state").exists() else None
        self.assertEqual(current_state, previous_state)

    def test_url_mode_treats_existing_file_as_input_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            input_file = tmp_path / "papers.txt"
            input_file.write_text("https://arxiv.org/pdf/2210.10732\n", encoding="utf-8")
            uv_log = tmp_path / "uv.log"

            (fake_bin / "uv").write_text(
                "#!/usr/bin/env bash\necho \"uv $*\" >> \"$UV_LOG\"\nexit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "git").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            os.chmod(fake_bin / "uv", 0o755)
            os.chmod(fake_bin / "git", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["UV_LOG"] = str(uv_log)
            env["PUBLIC_SYNC_ENABLED"] = "0"

            result = subprocess.run(
                ["bash", str(ROOT / "run_daily.sh"), "--url", str(input_file)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                f"uv run python jobs/ingest_url.py --from-file {input_file}",
                uv_log.read_text(encoding="utf-8"),
            )

    def _run_step_export(self, papers_status: int, obsidian_status: int):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            state = tmp_path / ".run_state"
            (fake_bin / "uv").write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    if [[ "$*" == *"jobs/export_papers.py --cloud"* ]]; then
                        exit "$PAPERS_STATUS"
                    fi
                    if [[ "$*" == *"jobs/export_obsidian_notes.py"* ]]; then
                        exit "$OBSIDIAN_STATUS"
                    fi
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            os.chmod(fake_bin / "uv", 0o755)

            script = tmp_path / "run_step_export.sh"
            script.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -e
                    STATE_FILE={state}
                    mark_state() {{
                        echo "test_run|$1|now" > "$STATE_FILE"
                    }}
                    maybe_mark_state() {{
                        mark_state "$1"
                    }}
                    {self._extract_step_export()}
                    step_export
                    """
                ),
                encoding="utf-8",
            )
            os.chmod(script, 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["PAPERS_STATUS"] = str(papers_status)
            env["OBSIDIAN_STATUS"] = str(obsidian_status)
            result = subprocess.run(["bash", str(script)], env=env, text=True, capture_output=True, check=False)
            state_text = state.read_text(encoding="utf-8") if state.exists() else None
            return result, state_text

    def _extract_step_export(self) -> str:
        script = (ROOT / "run_daily.sh").read_text(encoding="utf-8")
        match = re.search(r"^step_export\(\) \{.*?^\}", script, flags=re.MULTILINE | re.DOTALL)
        if not match:
            self.fail("Could not find step_export function")
        return match.group(0)


if __name__ == "__main__":
    unittest.main()
