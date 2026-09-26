from mimikr.examples import ExampleIndex, cut_exchanges, recent_query
from mimikr.transcript import Message
from test_evaluate import WordEmbedder


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


TOPICS = chat(
    "June: how was the kitchen shift", "Sam: chaos as usual",
    "June: want noodles for lunch", "Sam: noodles always",
    "June: did you watch the football match", "Sam: we lost again",
    "June: noodles or pizza tonight", "Sam: noodles obviously",
)


def test_select_returns_the_most_similar_exchanges_in_the_order_of_the_transcript():
    embed = WordEmbedder()
    index = ExampleIndex.build(TOPICS, "Sam", embed)
    chosen = index.select("any noodles later", embed, budget=120)
    assert [exchange.messages[-1].text for exchange in chosen] == ["noodles always", "noodles obviously"]


def test_select_keeps_to_the_budget():
    embed = WordEmbedder()
    index = ExampleIndex.build(TOPICS, "Sam", embed)
    [chosen] = index.select("any noodles later", embed, budget=60)
    assert chosen.cost() <= 60


def test_select_with_no_query_selects_nothing():
    embed = WordEmbedder()
    assert ExampleIndex.build(TOPICS, "Sam", embed).select("  ", embed, budget=1000) == []


def test_build_sends_the_queries_in_batches(monkeypatch):
    monkeypatch.setattr("mimikr.examples.BATCH", 3)
    embed = WordEmbedder()
    ExampleIndex.build(TOPICS, "Sam", embed)
    assert [len(call) for call in embed.calls] == [3, 1]


def test_the_query_is_the_last_messages_after_the_last_message_of_the_identity():
    messages = [(False, "old"), (True, "mine"), (False, "a"), (False, "b")]
    assert recent_query(messages) == "a\nb"
    assert recent_query([(False, "a"), (True, "mine")]) == ""
    assert recent_query([(False, str(n)) for n in range(6)], lead=2) == "4\n5"
