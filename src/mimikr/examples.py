"""Choose the parts of the transcript that go into the prompt as examples.

An exchange is one turn of the person and the messages of the other people
just before it. The messages before the turn are the query of the exchange:
the text that a new message must be similar to.
"""

from collections.abc import Callable
from dataclasses import dataclass

from mimikr.transcript import Message, turn_starts
from mimikr.vectors import cosine

Embedder = Callable[[list[str]], list[list[float]]]

# The number of texts in one request to the embedding server.
BATCH = 64

# The maximum number of messages of other people before a turn.
LEAD = 3


@dataclass
class Exchange:
    messages: list[Message]
    query: str

    def cost(self) -> int:
        """Return the number of characters that the exchange takes in the prompt."""
        return sum(len(message.speaker) + len(message.text) + 3 for message in self.messages) + 5


def cut_exchanges(transcript: list[Message], speaker: str, lead: int = LEAD) -> list[Exchange]:
    """Cut the transcript into exchanges. A turn with nothing before it has no exchange."""
    exchanges = []
    for start in turn_starts(transcript, speaker):
        first = start
        while first > 0 and start - first < lead and transcript[first - 1].speaker != speaker:
            first -= 1
        if first == start:
            continue
        end = start
        while end < len(transcript) and transcript[end].speaker == speaker:
            end += 1
        query = "\n".join(message.text for message in transcript[first:start])
        exchanges.append(Exchange(messages=transcript[first:end], query=query))
    return exchanges


def embed_all(texts: list[str], embed: Embedder) -> list[list[float]]:
    vectors: list[list[float]] = []
    for first in range(0, len(texts), BATCH):
        vectors += embed(texts[first : first + BATCH])
    return vectors


class ExampleIndex:
    """The exchanges of one identity, with an embedding of the query of each."""

    def __init__(self, exchanges: list[Exchange], vectors: list[list[float]]):
        self.exchanges = exchanges
        self.vectors = vectors

    @classmethod
    def build(cls, transcript: list[Message], speaker: str, embed: Embedder) -> "ExampleIndex":
        exchanges = cut_exchanges(transcript, speaker)
        return cls(exchanges, embed_all([exchange.query for exchange in exchanges], embed))

    def select(self, query: str, embed: Embedder, budget: int) -> list[Exchange]:
        """Return the exchanges most similar to the query that fit the budget.

        The result is in the order of the transcript, so that the model reads
        the conversations in the order that they happened.
        """
        if not self.exchanges or not query.strip():
            return []
        [target] = embed([query])
        ranked = sorted(range(len(self.exchanges)), key=lambda i: cosine(target, self.vectors[i]), reverse=True)
        chosen, used = [], 0
        for index in ranked:
            cost = self.exchanges[index].cost()
            if used + cost > budget:
                continue
            chosen.append(index)
            used += cost
        return [self.exchanges[index] for index in sorted(chosen)]


def recent_query(messages: list[tuple[bool, str]], lead: int = LEAD) -> str:
    """Return the text that the next reply answers.

    Each item is (from the identity, text). The query is the last messages of
    other people, after the last message of the identity.
    """
    texts: list[str] = []
    for mine, text in reversed(messages):
        if mine or len(texts) == lead:
            break
        texts.append(text)
    return "\n".join(reversed(texts))
