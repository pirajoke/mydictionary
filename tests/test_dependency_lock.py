import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DependencyLockTest(unittest.TestCase):
    def test_runtime_lock_is_exact_and_covers_direct_dependencies(self):
        lock_lines = [
            line.strip()
            for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        for line in lock_lines:
            with self.subTest(requirement=line):
                self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[^=\s]+$")

        locked_names = {
            re.split(r"==", line, maxsplit=1)[0].lower().replace("_", "-")
            for line in lock_lines
        }
        direct_names = set()
        for line in (ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name = re.split(r"[<>=]", line, maxsplit=1)[0].strip().lower()
            direct_names.add(re.sub(r"\[.*\]$", "", name).replace("_", "-"))
        self.assertTrue(direct_names.issubset(locked_names))

    def test_ci_and_release_builder_install_the_lock(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        deployer = (ROOT / "ops/mydictionary_autodeploy.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--requirement requirements.lock", workflow)
        self.assertIn('temporary / "requirements.lock"', deployer)


if __name__ == "__main__":
    unittest.main()
