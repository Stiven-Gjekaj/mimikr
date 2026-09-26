<div align="center">
  <a href="README.md"><b>mimikr</b></a>
</div>

# Contributing to mimikr

Thanks for your interest in mimikr, a desktop program that writes chat messages
in the style of a person, with a language model on your own computer.
Contributions of all kinds are welcome: bug reports, documentation fixes, new
chat importers, better style measurements, and arguments against a decision
that is already made.

The toolchain is Python and [uv](https://docs.astral.sh/uv/).

    uv sync
    uv run pytest
    uv run mimikr check

Those three are the gate.
The [README](README.md) says what is built so far.

## Ways to contribute

- Add an importer for the export of a chat application.
- Improve the style profile, so that it finds more of how a person writes.
- Improve the window.
- Report a model that ignores the style, with the settings that you used.
- Take on a phase from [docs/roadmap.md](docs/roadmap.md), or argue that the
  order is wrong, with the reason.

Before you start significant work, open an issue to agree on the approach.
This costs you one message and can save you a rewritten pull request.

## The rule that comes before all the others

**No real person goes into the repository.**

An identity holds the private messages of a real person.
A test, an example, an issue, and a pull request use invented people only.
`.gitignore` keeps `identities/` and `data/` out of the repository.
A pull request that removes those lines is refused.

## A test never calls a real model

A test that needs a model uses a fake one that returns a fixed text.
A real model is slow, it gives a different answer each time, and the machine
that runs the tests may not have one.

A test builds the identities that it needs inside itself, in a temporary
directory.
It never reads `examples/identities/`.
The examples are for people, and a change to an example must not break a test.

The window tests use the Qt `offscreen` platform, so they open no window and
run on a machine with no screen.

## Three traps that this project creates

**A test can pass for the wrong reason.**
A test of the style profile that gives messages with no emoji and checks for
"Do not use emoji." proves nothing if the profile says that for every input.
Give the test one input that must say it, and one that must not.

**The model can hide a fault in the prompt.**
A good model writes a good reply from a bad prompt.
Test the prompt itself: the roles, the order, and the text in it.
Do not test that a reply "sounds right".

**A size is not a state.**
A transcript with 2000 lines does not give 2000 examples to the model.
The prompt has a budget. Report what went into the prompt, not what was in the
file.

## What the code must never do

- Send data to a host other than the one in `base_url`.
- Write a file outside `data_dir`.
- Write identity data to a log.
- Show a reply as if the real person wrote it.
- Change the files of an identity with no action of the user. Only a save in
  the identity editor, or an import into an identity, writes them.
- Start a program that no setting names, or a server that listens on an
  address other than 127.0.0.1.

## Coding style

- Match the surrounding code. Small, focused functions and clear names beat
  cleverness.
- Keep the engine free of the window. `engine.py` knows no Qt, and that is the
  reason a test can run it.
- Add dependencies sparingly, and say in the pull request why the standard
  library or an existing dependency does not do the job.
- Prefer MIT, BSD and Apache 2.0 for a dependency. Say so in the pull request
  if a dependency has another licence.

## Commit messages and pull requests

[`AGENTS.md`](AGENTS.md) is the full set of rules. These four cause the most
rework.

- **One change per commit, and a feature is many commits.** A commit that says
  "integrate the full feature" is wrong even when the code is right. Split it
  into the steps that a reviewer can read and revert one at a time.
- **Code and its tests go in one commit. Documentation goes in its own.**
- **All text uses Simplified Technical English.** Short sentences, active voice,
  present tense. No em-dashes and no emoji, in source, comments, documentation,
  commit messages, or pull requests.
- **Write the subject in the present tense, with no version number.** A commit
  changes no version.

In the pull request, describe what changed and why, and say how you tested it.
If the change affects a reply, name the model that you tried it with.

## Reporting security issues

Do not open a public issue for a security problem.
See [SECURITY.md](SECURITY.md) for how to report it privately.

## Code of conduct

By taking part in this project you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
