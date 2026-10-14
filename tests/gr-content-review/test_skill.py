import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "gr-content-review"
SKILL = SKILL_DIR / "SKILL.md"
ACCEPTANCE = Path(__file__).with_name("review_acceptance.json")


def frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md 缺少 frontmatter"
    meta = {}
    key = None
    for line in match.group(1).splitlines():
        if re.match(r"^[a-z_]+:", line):
            key, _, value = line.partition(":")
            meta[key] = value.strip()
        elif key:
            meta[key] = (meta[key] + "\n" + line.strip()).strip()
    return meta


def test_frontmatter_name_matches_directory():
    meta = frontmatter(SKILL.read_text(encoding="utf-8"))
    assert meta["name"] == SKILL_DIR.name
    assert "English trigger:" in meta["description"]


def test_registered_in_marketplace_and_readme():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    skills = [s for plugin in market["plugins"] for s in plugin["skills"]]
    assert "./skills/gr-content-review" in skills
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert any(line.startswith("| `gr-content-review` |") for line in readme.splitlines())


def test_relative_links_resolve():
    text = SKILL.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)#]+)\)", text):
        if not target.startswith(("http://", "https://")):
            assert (SKILL_DIR / target).exists(), target


def test_output_template_fences_balanced():
    assert SKILL.read_text(encoding="utf-8").count("```") % 2 == 0


def test_acceptance_cases_well_formed():
    data = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    ids = [case["id"] for case in data["cases"]]
    assert len(ids) == len(set(ids))
    for case in data["cases"]:
        assert case["input"] and case["acceptance"]
