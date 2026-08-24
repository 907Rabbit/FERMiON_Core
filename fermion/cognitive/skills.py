"""Discovery and lightweight retrieval for repository SKILL.md procedures."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class DiscoveredSkill:
    name: str; path: Path; purpose: str

def discover_skills(root: str | Path) -> list[DiscoveredSkill]:
    skills = []
    for path in Path(root).rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        first = next((line.strip("# ") for line in text.splitlines() if line.strip()), path.parent.name)
        skills.append(DiscoveredSkill(path.parent.name, path, first[:180]))
    return sorted(skills, key=lambda item: str(item.path))

def retrieve_skills(query: str, skills: list[DiscoveredSkill], limit: int = 3) -> list[DiscoveredSkill]:
    words = set(query.lower().split())
    return sorted(skills, key=lambda skill: len(words & set((skill.name + " " + skill.purpose).lower().split())), reverse=True)[:limit]
