from mimikr.examples import cut_exchanges
from mimikr.transcript import Message


def chat(*lines: str) -> list[Message]:
    return [Message(*line.split(": ", 1)) for line in lines]


def test_an_exchange_is_the_messages_before_a_turn_and_the_turn():
    transcript = chat("Sam: hey", "June: a", "June: b", "Sam: c", "Sam: d", "June: e")
    [exchange] = cut_exchanges(transcript, "Sam")
    assert [m.text for m in exchange.messages] == ["a", "b", "c", "d"]
    assert exchange.query == "a\nb"


def test_the_lead_has_a_limit():
    transcript = chat("June: 1", "June: 2", "June: 3", "June: 4", "June: 5", "Sam: x")
    [exchange] = cut_exchanges(transcript, "Sam", lead=2)
    assert exchange.query == "4\n5"


def test_a_turn_with_nothing_before_it_has_no_exchange():
    assert cut_exchanges(chat("Sam: first", "June: q", "Sam: r"), "Sam")[0].query == "q"
    assert len(cut_exchanges(chat("Sam: first", "June: q", "Sam: r"), "Sam")) == 1
