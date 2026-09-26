import pytest

from mimikr.avatars import AvatarStore


def store(tmp_path) -> AvatarStore:
    (tmp_path / "identities" / "sam").mkdir(parents=True, exist_ok=True)
    return AvatarStore(tmp_path / "data", tmp_path / "identities")


def test_no_picture_is_none(tmp_path):
    assert store(tmp_path).find("identity", "sam") is None
    assert store(tmp_path).find("room", "abc123") is None


def test_a_picture_in_the_identity_directory_is_found(tmp_path):
    avatars = store(tmp_path)
    picture = tmp_path / "identities" / "sam" / "avatar.jpg"
    picture.write_bytes(b"jpg")
    assert avatars.find("identity", "sam") == picture


def test_a_chosen_picture_has_priority_and_its_removal_keeps_the_other(tmp_path):
    avatars = store(tmp_path)
    by_hand = tmp_path / "identities" / "sam" / "avatar.png"
    by_hand.write_bytes(b"png")
    chosen = avatars.path_for("identity", "sam")
    chosen.parent.mkdir(parents=True)
    chosen.write_bytes(b"png")
    assert avatars.find("identity", "sam") == chosen
    avatars.remove("identity", "sam")
    assert avatars.find("identity", "sam") == by_hand
    assert by_hand.is_file()


def test_rooms_and_identities_do_not_share_a_file(tmp_path):
    avatars = store(tmp_path)
    assert avatars.path_for("room", "sam") != avatars.path_for("identity", "sam")


@pytest.mark.parametrize("key", ["", "../x", "a/b", "a\\b", ".hidden"])
def test_a_name_cannot_leave_the_directory(tmp_path, key):
    with pytest.raises(ValueError):
        store(tmp_path).path_for("identity", key)


def test_an_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError, match="'identity' or 'room'"):
        store(tmp_path).path_for("user", "me")
