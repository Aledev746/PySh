# PySh

> A small, educational shell implemented from scratch in Python.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![CodeCrafters](https://img.shields.io/badge/CodeCrafters-Build_Your_Own_Shell-2ea44f?logo=github)](https://app.codecrafters.io/courses/shell/overview)

PySh is a compact, POSIX-inspired command-line shell built to make the mechanics of a shell easy to read and experiment with. It started as a solution to the [CodeCrafters Build Your Own Shell](https://app.codecrafters.io/courses/shell/overview) challenge and has grown into a focused implementation of parsing, built-ins, process execution, file-descriptor redirection, and pipelines.

The project favors clear control flow and the Python standard library over feature breadth. It is intended for learning, experimentation, and code reading—not as a replacement for Bash or another production shell.

## Highlights

- Interactive REPL with a `$ ` prompt and clean EOF handling.
- Quoted and escaped arguments, comments, and environment-variable expansion.
- Built-ins that can update the parent shell process: `cd`, `export`, and `unset`.
- External command lookup through `PATH` with meaningful exit statuses.
- Input, output, append, and stderr redirection.
- Multi-process pipelines connected with `|`.
- Standard-library unit tests for parsing and execution behavior.

## Supported commands

| Command | Purpose |
| --- | --- |
| `cd [directory]` | Change the current working directory. Defaults to `HOME`. |
| `pwd` | Print the current working directory. |
| `echo [-n] [args...]` | Write arguments to standard output. |
| `type command...` | Report whether a command is a built-in or an executable in `PATH`. |
| `export NAME=value...` | Set environment variables for the current session. |
| `unset NAME...` | Remove environment variables. |
| `help` | List the available built-ins. |
| `exit [status]` | Leave the shell with an optional status code. |

## Quick start

### Requirements

- Python 3.10 or newer
- A POSIX-like operating system such as Linux or macOS (`os.fork` is used for pipelines)
- `uv` is optional, but recommended by the included runner script

### Run locally

```bash
git clone https://github.com/Aledev746/PySh.git
cd PySh
./your_program.sh
```

Or run the module directly:

```bash
python3 -m app.main
```

## Examples

Once PySh is running, try:

```console
$ pwd
/home/user/PySh
$ echo "hello from PySh"
hello from PySh
$ printf 'hello\nworld\n' | tr a-z A-Z
HELLO
WORLD
$ echo "saved" > output.txt
$ cat output.txt
saved
$ export PROJECT=PySh
$ echo "Working on $PROJECT"
Working on PySh
```

Supported redirection operators are `<`, `>`, `>>`, `2>`, and `2>>` (spaces around the operator are optional). The shell also supports `$?` for the previous command's exit status.

## How it works

PySh keeps the execution path deliberately visible:

1. `lex` tokenizes a command line, removes quotes, handles escapes, and expands variables.
2. `parse` converts tokens into simple commands, redirections, and pipeline stages.
3. Built-ins that change shell state run in the parent process; other commands run in child processes.
4. `run_pipeline` connects child processes with Unix pipes and applies redirections with `dup2`.
5. External programs are resolved with `PATH` and started with `os.execvpe`.

### Project layout

```text
app/main.py       # Lexer, parser, built-ins, and process execution
tests/test_main.py # Unit tests for the shell behavior
your_program.sh   # Local CodeCrafters-compatible runner
.codecrafters/    # CodeCrafters compile and run scripts
pyproject.toml    # Project metadata and Python requirement
```

## Test suite

PySh uses the Python standard library, so the tests need no third-party dependencies:

```bash
python -m unittest discover -v
```

The tests cover quoting and expansion, operator parsing, syntax errors, built-ins, directory changes, and pipelines.

## Roadmap

- [x] Interactive prompt and external command execution
- [x] Built-ins: `echo`, `exit`, `type`, `cd`, `pwd`, `export`, `unset`, and `help`
- [x] Quoting, escaping, comments, and variable expansion
- [x] Input/output/stderr redirection
- [x] Pipelines
- [ ] Portable command history and tab completion
- [ ] Background jobs and job control
- [ ] More complete POSIX word splitting and expansion rules

## Contributing

PySh is a learning project and small, focused contributions are welcome. Before opening a pull request:

1. Keep the implementation in the standard library unless a dependency is essential.
2. Add or update a test for behavior changes.
3. Run `python -m unittest discover -v` locally.
4. Explain the shell behavior and trade-offs in the pull request description.

## Origin

This project is inspired by the [CodeCrafters Build Your Own Shell](https://app.codecrafters.io/courses/shell/overview) challenge. It is maintained as an educational implementation with readability and experimentation as its primary goals.
