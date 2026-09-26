from pathlib import Path

import pytest

from mimikr.identity import IdentityError, list_identities, load_identity


def make_identity(root: Path, name: str, personality: str = "A person.", chat: str | None = None,
                  settings: str | None = None) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "personality.md").write_text(personality, encoding="utf-8")
    if chat is not None:
        (directory / "chat.md").write_text(chat, encoding="utf-8")
    if settings is not None:
        (directory / "identity.toml").write_text(settings, encoding="utf-8")
    return directory


def test_loads_an_identity_with_no_chat(tmp_path):
    identity = load_identity(make_identity(tmp_path, "ana", personality="  Likes cats.  "))
    assert (identity.id, identity.display_name, identity.personality) == ("ana", "ana", "Likes cats.")
    assert identity.speaker is None
    assert identity.transcript == []


def test_matches_the_speaker_to_the_directory_name_in_any_case(tmp_path):
    identity = load_identity(make_identity(tmp_path, "ana", chat="Ana: hi\nBo: yo\nAna: bye"))
    assert identity.speaker == "Ana"
    assert identity.style.message_count == 2


def test_the_settings_file_sets_the_speaker_and_the_model(tmp_path):
    settings = 'display_name = "Ana"\nspeaker = "ana_92"\nmodel = "qwen2.5"\ntemperature = 0.3\n'
    identity = load_identity(make_identity(tmp_path, "a", chat="ana_92: hi", settings=settings))
    assert (identity.display_name, identity.speaker, identity.model, identity.temperature) == (
        "Ana", "ana_92", "qwen2.5", 0.3
    )


def test_refuses_a_chat_where_no_speaker_matches(tmp_path):
    with pytest.raises(IdentityError, match="The speakers are: Bo"):
        load_identity(make_identity(tmp_path, "ana", chat="Bo: hi"))


def test_refuses_a_directory_with_no_personality(tmp_path):
    (tmp_path / "ana").mkdir()
    with pytest.raises(IdentityError, match="personality.md"):
        load_identity(tmp_path / "ana")


def test_list_keeps_the_good_identities_and_reports_the_bad_ones(tmp_path):
    make_identity(tmp_path, "ana")
    make_identity(tmp_path, "bo", chat="Somebody: hi")
    (tmp_path / "notes").mkdir()
    identities, errors = list_identities(tmp_path)
    assert list(identities) == ["ana"]
    assert list(errors) == ["bo"]


def test_list_of_a_missing_directory_is_empty(tmp_path):
    assert list_identities(tmp_path / "missing") == ({}, {})
