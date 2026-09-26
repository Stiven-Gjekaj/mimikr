<div align="center">
  <a href="../README.md"><b>mimikr</b></a>
</div>

# Milestones

The first phase is built: the identity files, the style profile, the prompt,
the rooms, and the window.
[The roadmap](roadmap.md) says what comes next.
This file holds the decisions that shape the work, and the reason for each.
It also holds the options that lost, because the reason a choice lost is the
part that a later reader needs.

---

## The rule that decides everything else

**Nothing leaves the computer.**

An identity holds the private messages of a real person.
mimikr sends them to one place: the model server in `base_url`.
The default address is on the same computer.
The program has no account, no telemetry, and no update check.

The rule also decides the model API.
A local model server is the only kind of server that the default can name.

---

## The decisions

### Python

The model servers, the tokenizers and the embedding libraries all have a
Python interface first.
The work of this project is in the prompt, and a prompt changes many times a
day. Python makes each change short.

- **Rust** lost. It gives one fast binary, but the slow part is the model, and
  not the program. A change to the prompt costs a compile.
- **TypeScript** lost. It is good for a web interface, and the interface is not
  a web page.

### Any server with the OpenAI chat API

Ollama, LM Studio, the llama.cpp server, vLLM and many others give the same
`/v1/chat/completions` endpoint.
One client with one setting, `base_url`, works with all of them.

- **Only Ollama** lost. It is the simplest to start, but it ties the user to
  one server.
- **llama.cpp in the process** lost. It needs no server, but it adds a large
  native dependency, and each new model format needs a new build.

### A native window with PySide6

The user asked for a native program and not a web page.
PySide6 is the Qt library for Python, from the Qt Company.
It draws native controls on macOS, on Windows and on Linux, and its licence is
the LGPL version 3.

- **A web interface in the browser** lost. The first version had one, with
  FastAPI and a WebSocket. It needed a server, a port and a browser for a
  program that one person uses on one computer.
- **Tkinter** lost. It comes with Python, but its controls do not look native
  and it has no good text layout for chat bubbles.
- **PyQt6** lost. It is the same Qt, but its licence is the GPL.
- **wxPython, Kivy and Flet** lost. Each is smaller, and each has fewer controls
  or a less native look than Qt.

### `Name: message` lines

A person can write the format by hand.
Each chat application can export to it with a short script.

- **A heading for each speaker** lost. It shows long messages well, but
  hand-written chats are mostly short lines.
- **The raw exports** lost for now. Each application has its own format, and
  each format changes. An importer for each export comes later, and it writes
  `Name: message` lines.

### English transcripts only

The transcripts are in English, and mimikr supports no other language.
The style profile, the prompt, and the choice of model assume English.

- **Support for other languages** lost. It makes each measurement of the style
  depend on the language, and it takes away the models that are strong in
  English only. No user needs it.

### Rooms

A conversation is a room.
A room holds the user and one or more identities.
The name is "room" and not "chat", because identities also talk to each other
in a room.
`Next speaker` lets the members talk in turn.

### A measured style profile

`style.py` counts things in the transcript: the length of a message, capitals,
periods, emoji, repeated short replies, and messages in a row.
Then it writes each result as one plain instruction.

A model copies the style of examples, but a small local model copies it badly.
A plain instruction such as "Do not put a period at the end of a message" helps
a small model more than ten examples do.
The two go into the prompt together.

- **Examples only** lost, for the reason above.
- **A model that writes the profile** lost for now. It costs one call to the
  model for each identity, and a count gives the same facts with no model.

### The most recent examples, in a budget

The prompt holds the most recent part of the transcript that fits in 6000
characters.
Recent messages show how the person writes now.

This is a first step. [The roadmap](roadmap.md) replaces it with examples that
are similar to the current message.

### A model call that blocks, in a worker thread

The model client blocks. The window starts a thread for each turn, and the
thread sends each new message to the window through a Qt signal.

- **asyncio with qasync** lost. It joins the event loop of Qt and the event loop
  of asyncio, and that adds a dependency for one call at a time.

### Many short messages from one reply

Many people send three short messages and not one long one.
If the transcript shows that, the prompt asks for one message on each line,
and the program makes one message from each line.
