import pytest

from mimikr.editing import (
    EditError,
    create_identity,
    directory_name,
    read_settings,
    save_chat,
    save_personality,
    save_settings,
)
from mimikr.identity import load_identity
from mimikr.transcript import Message


def test_the_directory_name_is_safe():
    assert directory_name("  June Park! ") == "june-park"
    assert directory_name("../../etc") == "etc"
    with pytest.raises(EditError):
        directory_name("!!!")


def test_a_new_identity_loads(tmp_path):
    directory = create_identity(tmp_path, "June Park", "A teacher.")
    identity = load_identity(directory)
    assert (identity.id, identity.display_name, identity.personality) == ("june-park", "June Park", "A teacher.")


def test_a_new_identity_does_not_replace_one(tmp_path):
    create_identity(tmp_path, "June")
    with pytest.raises(EditError, match="already"):
        create_identity(tmp_path, "june")


def test_save_settings_changes_and_removes_keys_and_keeps_the_others(tmp_path):
    (tmp_path / "identity.toml").write_text('display_name = "Sam"\ncolor = "red"\n', encoding="utf-8")
    save_settings(tmp_path, {"model": "mistral-nemo", "temperature": 0.7, "display_name": ""})
    assert read_settings(tmp_path) == {"model": "mistral-nemo", "temperature": 0.7, "color": "red"}


def test_save_chat_writes_the_transcript_and_the_speaker(tmp_path):
    directory = create_identity(tmp_path, "Sam")
    messages = [Message("June", "you up"), Message("sam.cooks", "unfortunately")]
    save_chat(directory, messages, "sam.cooks")
    identity = load_identity(directory)
    assert identity.speaker == "sam.cooks" and identity.style.message_count == 1


def test_save_chat_refuses_to_write_over_a_chat_unless_asked(tmp_path):
    directory = create_identity(tmp_path, "Sam")
    (directory / "chat.md").write_text("Sam: keep me\n", encoding="utf-8")
    messages = [Message("Sam", "new")]
    with pytest.raises(EditError, match="exists"):
        save_chat(directory, messages, "Sam")
    save_chat(directory, messages, "Sam", replace=True)
    assert (directory / "chat.md").read_text(encoding="utf-8") == "Sam: new\n"


def test_save_chat_needs_a_message_of_the_speaker(tmp_path):
    directory = create_identity(tmp_path, "Sam")
    with pytest.raises(EditError, match="no message is from 'Sam'"):
        save_chat(directory, [Message("June", "hi")], "Sam")


def test_the_personality_needs_text(tmp_path):
    directory = create_identity(tmp_path, "Sam")
    with pytest.raises(EditError):
        save_personality(directory, "   ")
    save_personality(directory, "  A cook.  ")
    assert load_identity(directory).personality == "A cook."
