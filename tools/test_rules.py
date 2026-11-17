"""Static checks on the agent rules (AGENTS.md, .claude/settings.json), setup.sh and the README guide."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def denied(cmd):
    """True if a deny rule of the form `Bash(<prefix> *)` covers the command."""
    for rule in json.loads(read(".claude/settings.json"))["permissions"]["deny"]:
        prefix = re.fullmatch(r"Bash\(([^*]+) \*\)", rule).group(1)  # also checks the rule shape
        if cmd == prefix or cmd.startswith(prefix + " "):
            return True
    return False


class DenyRules(unittest.TestCase):
    def test_installs_and_remote_code_are_denied(self):
        for cmd in ("pnpm dlx cowsay hi", "npx cowsay hi", "pip install requests", "brew install jq",
                    "git clone https://github.com/octocat/Hello-World", "docker pull alpine",
                    "npm install left-pad", "pnpm add -g x", "pnpm install", "yarn add x", "bunx x",
                    "uv pip install x", "uv add x", "uvx ruff", "uv tool install x", "pipx install x",
                    "python -m pip install x", "python3 -m pip install x", ".venv/bin/python -m pip install x",
                    "cargo install x", "go install x@latest", "gem install x", "docker run alpine",
                    "wget https://example.com/x.sh"):
            self.assertTrue(denied(cmd), cmd)

    def test_repo_commands_stay_allowed(self):
        for cmd in ("scripts/smoke.sh fake", "../.venv/bin/python -m unittest -v", "python3 -m venv .venv",
                    "curl http://127.0.0.1:18765/health", "git status", "shellcheck scripts/setup.sh",
                    'grep -nE "pip install|npx|pnpm" README.md'):
            self.assertFalse(denied(cmd), cmd)


class RuleFiles(unittest.TestCase):
    def test_agents_md_states_the_rule(self):
        text = read("AGENTS.md")
        for needle in ("pnpm dlx", "npx", "pip install", "brew install", "curl ... | sh", "git clone",
                       "requirements.txt", "Allowed", "127.0.0.1", "Stop", "human", "sub-agents"):
            self.assertIn(needle, text, needle)

    def test_claude_and_gemini_import_agents_md(self):
        for name in ("CLAUDE.md", "GEMINI.md"):
            self.assertEqual(read(name).strip(), "@AGENTS.md", name)

    def test_setup_downloads_nothing(self):
        setup = read("scripts/setup.sh")
        self.assertNotRegex(setup, r"\buv\b|brew|pip|curl")
        self.assertIn("python3 -m venv .venv", setup)

    def test_requirements_has_no_dependency(self):
        lines = [x for x in read("requirements.txt").splitlines() if x.strip() and not x.startswith("#")]
        self.assertEqual(lines, [])


class Guide(unittest.TestCase):
    README = read("README.md")

    def test_no_install_commands(self):
        self.assertNotRegex(self.README, r"\buv\b|brew install|pip install|npx|pnpm")

    def test_old_sections_are_gone(self):
        for name in ("Layout", "Risk guards", "Live gate", "Rollout"):
            self.assertNotRegex(self.README, rf"(?m)^#+ {name}\b", name)
        self.assertLess(len(self.README.splitlines()), 120)

    def test_guide_keeps_what_the_owner_acts_on(self):
        for needle in ("scripts/setup.sh", "scripts/smoke.sh fake", "/health", "WebRequest code=200",
                       "Calendar ok=true values>0", "DRYRUN", "BRIDGE_ERR", "touch HALT", "Algo Trading",
                       "InpAllowLive=true", "GATE: PASS", "ExportM1", "ExportDeals", "(AGENTS.md)"):
            self.assertIn(needle, self.README, needle)
        self.assertLess(self.README.index("GATE: PASS"), self.README.index("InpAllowLive=true"))

    def test_names_exist_in_the_code(self):
        code = "".join(p.read_text(encoding="utf-8") for pat in ("scripts/*.sh", "run.sh", "bridge/server.py", "mt5/*.mq5")
                       for p in ROOT.glob(pat))
        for name in set(re.findall(r"\bInp\w+|\b[A-Z]{3,}_[A-Z_]{2,}\b", self.README)):
            self.assertIn(name, code, name)
        for script in set(re.findall(r"scripts/[\w-]+\.sh", self.README)):
            self.assertTrue((ROOT / script).exists(), script)


if __name__ == "__main__":
    unittest.main()
