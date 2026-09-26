<div align="center">
  <a href="../README.md"><b>mimikr</b></a>
</div>

# The roadmap

[docs/milestones.md](milestones.md) says what mimikr does and why.
This file says in what order to build it.

Each phase has a goal, the work in it, and an exit test.
The sizes are relative: S is a day or two, M is a week, and L is longer.

P1 is done. P2 is built, and its exit test passes with a fake model and a fake
embedding model. No real model has run it yet.

---

## The order, and the reason for it

**Measure first.**
A change to the prompt can make the replies better or worse, and a person who
reads ten replies cannot tell which.
So the score comes before the work that the score judges.

```mermaid
flowchart LR
    P1([P1 rooms and the window]) --> P2[P2 the score]
    P2 --> P3[P3 similar examples]
    P2 --> P4[P4 the choice of model]
    P1 --> P5[P5 importers]
    P1 --> P6[P6 live replies]
    P3 --> P7[P7 automatic rooms]
```

---

## P1: rooms and the window (done)

**Goal:** talk to one or more identities in a native window.

- Read `personality.md`, `chat.md` and `identity.toml`.
- Measure the style profile.
- Build the prompt, and split the reply into messages.
- Keep rooms on disk. Let the members reply in turn.
- Show the rooms in a PySide6 window.

**Exit test:** a room with two identities replies to the user, and `Next
speaker` lets the identities talk in turn. Tests with a fake model prove both.

## P2: the score (built)

**Goal:** a number that says how near the replies are to the person.

- Add `mimikr eval <identity>`.
- Keep the last part of `chat.md` apart. Give the model the conversation up to
  each real reply, and compare its reply with the real one.
- Compare the style: length, capitals, periods, emoji, messages in a row.
- Compare the meaning with a local embedding model.

**Exit test:** the score of the real replies against themselves is the best
score. The score of the replies of a different person is worse.

`tests/test_run_evaluation.py` holds the exit test. The real replies score 1
for style and 1 for meaning. One long, formal reply scores below 0.6 for style,
and below the baseline for meaning. Two more tests prove that the model never sees
the reply that it must write.

## P3: similar examples (M)

**Goal:** the examples in the prompt match the current message.

- Cut the transcript into short exchanges.
- Make an embedding of each exchange with a local model, and keep it on disk.
- For each new message, put the most similar exchanges into the prompt.

**Exit test:** the P2 score is better than with the most recent examples.

## P4: the choice of model (S)

**Goal:** a default model that the P2 score chose.

- Run the P2 score on three identities with each candidate model.
- Record the scores and the choice in [the milestones](milestones.md).

**Exit test:** the milestones hold the table of scores.

## P5: importers (M)

**Goal:** read the export of a chat application.

- WhatsApp, Telegram, Discord, and iMessage.
- Each importer writes `Name: message` lines.

**Exit test:** each importer reads an invented export and writes the expected
lines.

## P6: live replies (S)

**Goal:** the reply shows while the model writes it.

**Exit test:** the first words show before the model ends its reply.

## P7: automatic rooms (S)

**Goal:** the identities talk for a number of turns with no click.

**Exit test:** a room runs ten turns and stops. The user can stop it early.
