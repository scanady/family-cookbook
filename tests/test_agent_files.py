"""Where the AI coding assistants find the skills: .claude/skills and
.github/skills point at .agents/skills, as links where the system allows them
and as copies where it does not (Windows outside Developer Mode)."""
from pathlib import Path

from family_cookbook import scaffold


def test_links_refused_become_copies_that_update_refreshes(tmp_path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise OSError("A required privilege is not held by the client")

    monkeypatch.setattr(Path, "symlink_to", refuse)
    scaffold.install_agent_files(tmp_path, update=False)
    skills = sorted(p.name for p in (tmp_path / ".agents" / "skills").iterdir())
    for copy in (tmp_path / ".claude" / "skills", tmp_path / ".github" / "skills"):
        assert not copy.is_symlink()
        assert sorted(p.name for p in copy.iterdir()) == skills

    # The family's own skill beside the copies survives an update; a stale engine file is refreshed.
    own = tmp_path / ".claude" / "skills" / "our-own-skill"
    own.mkdir()
    stale = tmp_path / ".claude" / "skills" / skills[0] / "SKILL.md"
    stale.write_text("old", encoding="utf-8")
    scaffold.install_agent_files(tmp_path, update=True)
    assert own.is_dir()
    assert stale.read_text(encoding="utf-8") != "old"
