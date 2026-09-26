import pytest

from mimikr.rooms import USER, Room, RoomMessage, RoomStore, search_rooms


def test_the_store_saves_and_loads_a_room(tmp_path):
    store = RoomStore(tmp_path)
    room = store.create("Friends", ["ana", "bo"])
    room.messages.append(RoomMessage(author=USER, name="You", text="hi ✨"))
    store.save(room)
    loaded = store.get(room.id)
    assert loaded == room
    assert [r.id for r in store.list()] == [room.id]


def test_the_store_deletes_a_room(tmp_path):
    store = RoomStore(tmp_path)
    room = store.create("Friends", ["ana"])
    store.delete(room.id)
    with pytest.raises(KeyError):
        store.get(room.id)


def test_the_store_refuses_an_id_that_is_a_path(tmp_path):
    with pytest.raises(KeyError):
        RoomStore(tmp_path).get("../secret")


def test_the_first_member_speaks_first():
    assert Room("r", ["ana", "bo"]).next_speaker() == "ana"


def test_the_members_speak_in_turn_and_the_user_does_not_change_the_turn():
    room = Room("r", ["ana", "bo", "cy"])
    room.messages.append(RoomMessage(author="bo", name="Bo", text="x"))
    room.messages.append(RoomMessage(author=USER, name="You", text="y"))
    assert room.next_speaker() == "cy"
    room.messages.append(RoomMessage(author="cy", name="Cy", text="z"))
    assert room.next_speaker() == "ana"


def search_fixture():
    late = Room("Late night", ["june", "sam"])
    late.messages = [RoomMessage(USER, "You", "noodles?"), RoomMessage("sam", "Sam", "NOODLES always")]
    work = Room("Work", ["ana"])
    work.messages = [RoomMessage(USER, "You", "the report is late")]
    return [late, work], {"june": "June", "sam": "Sam", "ana": "Ana"}


def test_search_counts_the_matching_messages_with_no_case():
    rooms, names = search_fixture()
    assert [(room.name, hits) for room, hits in search_rooms(rooms, "Noodles", names)] == [("Late night", 2)]


def test_search_finds_a_room_by_its_name_or_a_member():
    rooms, names = search_fixture()
    assert [(room.name, hits) for room, hits in search_rooms(rooms, "late", names)] == [("Late night", 0), ("Work", 1)]
    assert [room.name for room, _ in search_rooms(rooms, "ana", names)] == ["Work"]


def test_an_empty_search_keeps_each_room():
    rooms, names = search_fixture()
    assert len(search_rooms(rooms, "  ", names)) == 2
