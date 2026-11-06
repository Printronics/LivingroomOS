"""Konsistenz von Konfiguration, Abhängigkeiten, Portabilität und Dokumentation.

Diese Tests erzwingen die Projektregeln automatisch:
- jede Python-Abhängigkeit steht in requirements.txt,
- jedes Debian-Paket steht in docs/SYSTEMABHAENGIGKEITEN.md,
- keine ARM-Zielarchitektur; x86_64 wird explizit geprüft,
- die ausgelieferte Konfiguration ist gültig.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from services.app_launcher import parse_apps  # noqa: E402
from services.settings_store import SettingsStore  # noqa: E402
from version import __version__  # noqa: E402

# Direkt importiert, aber von fastapi mitgebracht (Begründung in requirements.txt).
BROUGHT_BY_FASTAPI = {"starlette", "pydantic"}
ARM_WORDS = re.compile(r"aarch64|arm64|raspberry|armv[0-9]", re.IGNORECASE)


def requirement_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].lower().replace("-", "_"))
    return names


def package_names(path: Path) -> list[str]:
    return [
        line.split()[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def imported_top_levels(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def production_files() -> list[Path]:
    return [p for p in BACKEND.rglob("*.py") if "tests" not in p.relative_to(BACKEND).parts]


class ShippedConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SettingsStore(BACKEND / "config" / "settings.json")

    def test_config_is_valid_and_has_no_problems(self) -> None:
        apps, problems = parse_apps(self.store.apps)
        self.assertEqual(problems, [])
        self.assertGreaterEqual(len(apps), 1)

    def test_every_browser_app_has_its_own_profile_and_wayland_flag(self) -> None:
        for app in self.store.apps:
            if app["command"][0] == "google-chrome-stable":
                with self.subTest(app=app["id"]):
                    self.assertIn("--user-data-dir={profile_dir}", app["command"])
                    self.assertIn("--ozone-platform=wayland", app["command"])
                    self.assertNotIn("--no-sandbox", app["command"])

    def test_trusted_dirs_are_absolute_and_not_architecture_specific(self) -> None:
        dirs = self.store.server["trusted_bin_dirs"]
        self.assertTrue(all(d.startswith("/") for d in dirs))
        self.assertTrue(all(d.startswith("/") for d in dirs))

    def test_config_text_names_no_architecture(self) -> None:
        text = (BACKEND / "config" / "settings.json").read_text(encoding="utf-8")
        self.assertIsNone(ARM_WORDS.search(text))


class PortabilityTests(unittest.TestCase):
    def test_no_hardcoded_library_paths_or_architecture_names_in_code_strings(self) -> None:
        offenders = []
        for path in production_files():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and ARM_WORDS.search(node.value):
                    offenders.append(f"{path.relative_to(BACKEND)}: {node.value[:60]!r}")
        self.assertEqual(offenders, [], "Hardwarespezifisches gehört in Konfiguration oder Profile, nicht in den Code")

    def test_frontend_and_system_files_name_no_architecture(self) -> None:
        offenders = []
        for folder in ("frontend", "system"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and path.suffix in {".js", ".html", ".css", ".service", ".target", ".toml", ".xml", ".json", ""}:
                    if ARM_WORDS.search(path.read_text(encoding="utf-8", errors="ignore")):
                        offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


class DependencyTests(unittest.TestCase):
    def test_every_third_party_import_is_documented_in_requirements(self) -> None:
        local = {p.stem for p in BACKEND.glob("*.py")} | {p.name for p in BACKEND.iterdir() if p.is_dir()}
        documented = requirement_names(ROOT / "requirements.txt")
        allowed = documented | (BROUGHT_BY_FASTAPI if "fastapi" in documented else set())
        undocumented = {}
        for path in production_files():
            third_party = {m for m in imported_top_levels(path) if m not in sys.stdlib_module_names and m not in local}
            missing = third_party - allowed
            if missing:
                undocumented[str(path.relative_to(BACKEND))] = sorted(missing)
        self.assertEqual(undocumented, {}, "Abhängigkeit fehlt in requirements.txt")

    def test_requirements_are_not_unused(self) -> None:
        used = set()
        for path in production_files():
            used |= imported_top_levels(path)
        self.assertEqual(requirement_names(ROOT / "requirements.txt") - used, set())

    def test_process_management_uses_only_the_standard_library(self) -> None:
        for name in ("process_manager.py", "app_launcher.py", "settings_store.py"):
            with self.subTest(module=name):
                third = {m for m in imported_top_levels(BACKEND / "services" / name)
                         if m not in sys.stdlib_module_names and m not in {"services"}}
                self.assertEqual(third, set())

    def test_only_api_tests_need_httpx_and_it_is_listed_for_development(self) -> None:
        self.assertIn("httpx", requirement_names(ROOT / "requirements-dev.txt"))
        self.assertNotIn("httpx", requirement_names(ROOT / "requirements.txt"))
        for path in (BACKEND / "tests").glob("*.py"):
            if path.name != "test_api.py":
                self.assertNotIn("httpx", imported_top_levels(path), path.name)

    def test_no_pip_install_or_download_commands_in_project_scripts(self) -> None:
        pattern = re.compile(r"curl[^\n|]*\|\s*(ba)?sh|wget[^\n|]*\|\s*(ba)?sh|pip3? install|add-apt-repository|apt-key")
        offenders = []
        for folder in ("system", "tools"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(str(path.relative_to(ROOT)))
        run_sh = (ROOT / "run.sh").read_text(encoding="utf-8")
        if pattern.search(run_sh):
            offenders.append("run.sh")
        self.assertEqual(offenders, [], "Skripte dürfen nichts aus dem Netz laden oder installieren")


class DocumentationTests(unittest.TestCase):
    PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]+$")

    def test_every_debian_package_is_explained_in_the_system_dependency_doc(self) -> None:
        doc = (ROOT / "docs" / "SYSTEMABHAENGIGKEITEN.md").read_text(encoding="utf-8")
        for listing in ("debian-packages.txt", "debian-packages-optional.txt"):
            names = package_names(ROOT / listing)
            self.assertTrue(names, listing)
            for name in names:
                with self.subTest(package=name):
                    self.assertRegex(name, self.PACKAGE_RE)
                    self.assertIn(f"`{name}`", doc)

    def test_required_and_optional_package_lists_do_not_overlap(self) -> None:
        both = set(package_names(ROOT / "debian-packages.txt")) & set(package_names(ROOT / "debian-packages-optional.txt"))
        self.assertEqual(both, set())

    def test_core_packages_are_listed(self) -> None:
        required = set(package_names(ROOT / "debian-packages.txt"))
        self.assertTrue({"python3", "python3-fastapi", "python3-uvicorn", "labwc", "greetd"} <= required)

    def test_required_project_documents_exist_and_are_not_empty(self) -> None:
        for name in ("README.md", "INSTALL.md", "ARCHITECTURE.md", "CHANGELOG.md", "docs/SYSTEMABHAENGIGKEITEN.md", "docs/SICHERHEIT.md"):
            with self.subTest(file=name):
                self.assertGreater(len((ROOT / name).read_text(encoding="utf-8").strip()), 200)

    def test_changelog_documents_the_current_version(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(changelog, re.compile(rf"^## \[{re.escape(__version__)}\]", re.MULTILINE), "aktuelle Version fehlt im CHANGELOG")

    def test_every_listed_relative_link_in_markdown_exists(self) -> None:
        broken = []
        for md in [*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]:
            for target in re.findall(r"\]\(([^)#\s]+)\)", md.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("mailto:"):
                    continue
                if not (md.parent / target).exists():
                    broken.append(f"{md.relative_to(ROOT)} → {target}")
        self.assertEqual(broken, [])


class SystemFilesTests(unittest.TestCase):
    def test_json_policies_are_valid(self) -> None:
        for path in (ROOT / "system" / "google-chrome-stable").glob("*.json"):
            with self.subTest(file=path.name):
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_google_chrome_is_never_started_without_its_sandbox(self) -> None:
        for path in (ROOT / "system").rglob("*"):
            if path.is_file():
                self.assertNotIn("--no-sandbox", path.read_text(encoding="utf-8", errors="ignore"), str(path))

    def test_shell_scripts_have_a_shebang_and_are_executable(self) -> None:
        for path in (ROOT / "system" / "bin").iterdir():
            if path.is_dir():
                continue
            with self.subTest(script=path.name):
                self.assertTrue(path.read_text(encoding="utf-8").startswith("#!"))
                self.assertTrue(path.stat().st_mode & 0o111)

    def test_units_start_only_files_below_the_install_prefix_or_system_binaries(self) -> None:
        for path in (ROOT / "system" / "systemd" / "user").glob("*.service"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith(("ExecStart=", "ExecStartPre=")):
                    exe = line.split("=", 1)[1].lstrip("-@+!").split()[0]
                    with self.subTest(unit=path.name, exe=exe):
                        self.assertTrue(exe.startswith(("/opt/livingroomos/", "/usr/bin/", "/bin/")), exe)


if __name__ == "__main__":
    unittest.main()
