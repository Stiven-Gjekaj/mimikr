"""Choose the parts of the transcript that go into the prompt as examples.

An exchange is one turn of the person and the messages of the other people
just before it. The messages before the turn are the query of the exchange:
the text that a new message must be similar to.
"""

from dataclasses import dataclass

from mimikr.transcript import Message, turn_starts

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
