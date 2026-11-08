from skills import available_skills, load_skill_instructions


def test_directory_skill_is_discovered_and_loaded():
    skills = available_skills()
    assert "risk_first" in skills
    assert "market_structure" in skills
    assert "test" not in skills
    assert "risk-first" in load_skill_instructions("risk_first")
    assert "range" in load_skill_instructions("market_structure")


def test_legacy_text_file_skill_remains_supported(tmp_path, monkeypatch):
    import skills

    (tmp_path / "legacy.txt").write_text("Legacy instructions", encoding="utf-8")
    (tmp_path / "folder-skill").mkdir()
    (tmp_path / "folder-skill" / "instructions.txt").write_text(
        "Folder instructions", encoding="utf-8"
    )
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path)

    assert "legacy" in available_skills()
    assert "folder-skill" in available_skills()
    assert load_skill_instructions("legacy") == "Legacy instructions"
    assert load_skill_instructions("folder-skill") == "Folder instructions"
