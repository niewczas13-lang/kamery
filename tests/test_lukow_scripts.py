from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LukowScriptTests(unittest.TestCase):
    def test_start_script_runs_backend_and_frontend_hidden_with_pid_files(self) -> None:
        script = (ROOT / "scripts" / "start_lukow_panel.ps1").read_text(encoding="utf-8")

        self.assertIn("runtime\\pids", script)
        self.assertIn("backend.pid", script)
        self.assertIn("frontend.pid", script)
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("-RedirectStandardOutput", script)
        self.assertIn("-RedirectStandardError", script)
        self.assertNotIn("-NoExit", script)

    def test_stop_script_and_bat_stop_recorded_background_processes(self) -> None:
        script_path = ROOT / "scripts" / "stop_lukow_panel.ps1"
        bat_path = ROOT / "STOP_PANEL_LUKOW.bat"

        self.assertTrue(script_path.exists())
        self.assertTrue(bat_path.exists())
        script = script_path.read_text(encoding="utf-8")
        bat = bat_path.read_text(encoding="utf-8")

        self.assertIn("backend.pid", script)
        self.assertIn("frontend.pid", script)
        self.assertIn("Stop-LukowProcessTree", script)
        self.assertIn("ParentProcessId", script)
        self.assertIn("Stop-Process", script)
        self.assertIn("docker compose stop", script)
        self.assertIn("stop_lukow_panel.ps1", bat)

    def test_start_bats_return_after_background_launch(self) -> None:
        for bat_name in ("START_PANEL_LUKOW.bat", "START_NVR_LUKOW.bat"):
            with self.subTest(bat=bat_name):
                bat = (ROOT / bat_name).read_text(encoding="utf-8")

                self.assertIn("start_lukow_panel.ps1", bat)
                self.assertNotIn("pause", bat.lower())

    def test_lukow_powershell_scripts_parse(self) -> None:
        command = (
            "$files=@('.\\scripts\\start_lukow_panel.ps1','.\\scripts\\stop_lukow_panel.ps1');"
            "foreach($file in $files){"
            "$tokens=$null;$errors=$null;"
            "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $file),[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count -gt 0){$errors|ForEach-Object{$_.Message};exit 1}"
            "}"
        )

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
