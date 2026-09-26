<div align="center">
  <a href="README.md"><b>mimikr</b></a>
</div>

# Security Policy

## Supported versions

mimikr has no release.
When it has one, fixes go to the latest version on the default branch.
Older versions are not maintained.

## Reporting a vulnerability

Report security problems privately, and not through a public issue.

- Preferred: open a private security advisory with the "Report a vulnerability"
  button on the Security tab of this repository.
- Alternative: email the maintainer at stivenagostingjekaj@gmail.com.

Include the steps to reproduce, the affected commit, and the impact as you
understand it.
You can expect a first answer within a few days.
Your report gets an acknowledgement when the fix ships, unless you prefer to
stay anonymous.

## The threat model

Read this before you report.

**The data is the asset.**
An identity holds a description of a real person and a transcript of the
private messages of that person.
A room holds the conversations of the user with those identities.
The worst outcome is that this data leaves the computer without the choice of
the user.

**The data goes to one place only.**
The Software sends a request to the model server in the setting `base_url`,
and to no other host.
The default address is on the same computer.
A request to any other host is a vulnerability.

**The files stay in their directories.**
The Software reads identities from `identities_dir`, and it writes rooms,
pictures and logs into `data_dir`. It writes into `identities_dir` only when the
user saves in the identity editor or imports a chat. It writes `mimikr.toml`
when the user saves the settings, and an export where the user chooses.

**The Software can start llama-server.**
It starts the program in the setting `llama_server`, or the llama-server that
the system finds, and it tells each server to listen on 127.0.0.1 only.

**The transcript is untrusted text.**
A transcript can hold text that tells the model to do something.
The model has no tools, so that text can change only the reply.

**These are in scope:**

- A request that goes to a host other than `base_url`.
- A log, a crash report, or a temporary file that holds identity data outside
  `data_dir`.
- A room id, an identity name, or a file name that makes the Software read or
  write a file outside its directories.
- A crafted `chat.md`, `identity.toml`, or room file that crashes or hangs the
  Software, or that makes it run code.
- A change to `.gitignore` or to the defaults that puts identity data into the
  repository.
- A way to make the Software start a program that no setting names.
- A server that the Software starts, and that listens on an address other than
  127.0.0.1.

**These are out of scope:**

- A reply of the model that is wrong, rude, or harmful. That is the model, and
  [TERMS.md](TERMS.md) section 6 says so.
- Data that goes to a remote model server that the user set in `base_url`.
- A person with access to the user account who reads the files. The Software
  does not encrypt them.
- A program that the user names in the setting `llama_server`. The Software
  runs the program that the user chose.
- Findings from an automated scanner with no working demonstration.
