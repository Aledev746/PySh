"""PySh: a small, educational POSIX-like shell.

The implementation intentionally stays compact, but keeps the shell split into
four understandable pieces: lexing, parsing, built-ins, and process execution.
It is not intended to replace a full POSIX shell; it implements the features
documented by this project and the CodeCrafters shell stages.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from shutil import which
from typing import TextIO


BUILTINS = {
    "cd",
    "echo",
    "exit",
    "export",
    "help",
    "pwd",
    "type",
    "unset",
}

VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ShellSyntaxError(ValueError):
    """Raised when a command cannot be parsed."""


class ExitShell(Exception):
    """Internal signal used to exit the parent shell process."""

    def __init__(self, status: int = 0) -> None:
        self.status = status


@dataclass
class Redirect:
    fd: int
    operator: str
    target: str


@dataclass
class SimpleCommand:
    argv: list[str]
    redirects: list[Redirect]


def expand_variables(text: str, last_status: int) -> str:
    """Expand the small, useful subset of shell parameters supported by PySh."""

    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "$":
            result.append(text[index])
            index += 1
            continue

        if index + 1 >= len(text):
            result.append("$")
            index += 1
            continue

        if text[index + 1] == "?":
            result.append(str(last_status))
            index += 2
            continue

        if text[index + 1] == "$":
            result.append(str(os.getpid()))
            index += 2
            continue

        if text[index + 1] == "{":
            closing = text.find("}", index + 2)
            if closing == -1:
                result.append("$")
                index += 1
                continue
            name = text[index + 2 : closing]
            result.append(os.environ.get(name, "") if VARIABLE_NAME.fullmatch(name) else "")
            index = closing + 1
            continue

        match = VARIABLE_NAME.match(text, index + 1)
        if match:
            result.append(os.environ.get(match.group(0), ""))
            index = match.end()
        else:
            result.append("$")
            index += 1

    return "".join(result)


def lex(line: str, last_status: int = 0) -> list[str]:
    """Turn one command line into words and shell operators.

    Quotes are removed here, while expansion is performed only outside single
    quotes. Operators inside quotes remain ordinary characters.
    """

    tokens: list[str] = []
    current: list[str] = []
    token_started = False
    index = 0
    quote: str | None = None

    def flush() -> None:
        nonlocal token_started
        if token_started:
            tokens.append("".join(current))
            current.clear()
            token_started = False

    while index < len(line):
        char = line[index]

        if quote == "'":
            if char == "'":
                quote = None
            else:
                current.append(char)
            token_started = True
            index += 1
            continue

        if quote == '"':
            if char == '"':
                quote = None
                index += 1
                continue
            if char == "\\" and index + 1 < len(line) and line[index + 1] in '\\"$':
                current.append(line[index + 1])
                token_started = True
                index += 2
                continue
            if char == "$":
                start = index
                index += 1
                while index < len(line) and (line[index].isalnum() or line[index] in "_?{}"):
                    index += 1
                current.append(expand_variables(line[start:index], last_status))
                token_started = True
                continue
            current.append(char)
            token_started = True
            index += 1
            continue

        if char in " \t\r\n":
            flush()
            index += 1
            continue
        if char == "'":
            quote = char
            token_started = True
            index += 1
            continue
        if char == '"':
            quote = char
            token_started = True
            index += 1
            continue
        if char == "\\":
            if index + 1 < len(line):
                current.append(line[index + 1])
                token_started = True
                index += 2
            else:
                current.append("\\")
                token_started = True
                index += 1
            continue
        if char == "#":
            if not token_started:
                break
            current.append(char)
            index += 1
            continue

        # Redirection operators must be recognized before ordinary words.
        if not current and char == "2" and index + 1 < len(line) and line[index + 1] == ">":
            flush()
            if index + 2 < len(line) and line[index + 2] == ">":
                tokens.append("2>>")
                index += 3
            else:
                tokens.append("2>")
                index += 2
            continue
        if char == ">":
            flush()
            if index + 1 < len(line) and line[index + 1] == ">":
                tokens.append(">>")
                index += 2
            else:
                tokens.append(">")
                index += 1
            continue
        if char in "|<":
            flush()
            tokens.append(char)
            index += 1
            continue
        if char == "$":
            start = index
            index += 1
            if index < len(line) and line[index] == "{":
                end = line.find("}", index + 1)
                index = len(line) if end == -1 else end + 1
            elif index < len(line) and line[index] in "?$":
                index += 1
            else:
                match = VARIABLE_NAME.match(line, index)
                if match:
                    index = match.end()
            current.append(expand_variables(line[start:index], last_status))
            token_started = True
            continue

        current.append(char)
        token_started = True
        index += 1

    if quote is not None:
        raise ShellSyntaxError("unterminated quote")
    flush()
    return tokens


def parse(line: str, last_status: int = 0) -> list[SimpleCommand]:
    """Parse one line into a pipeline of simple commands."""

    tokens = lex(line, last_status)
    if not tokens:
        return []

    pipeline: list[SimpleCommand] = []
    command = SimpleCommand(argv=[], redirects=[])
    redirect_ops = {
        ">": (1, ">"),
        ">>": (1, ">>"),
        "<": (0, "<"),
        "2>": (2, ">"),
        "2>>": (2, ">>"),
    }

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "|":
            if not command.argv:
                raise ShellSyntaxError("empty command in pipeline")
            pipeline.append(command)
            command = SimpleCommand(argv=[], redirects=[])
            index += 1
            continue
        if token in redirect_ops:
            if index + 1 >= len(tokens) or tokens[index + 1] in {"|", *redirect_ops}:
                raise ShellSyntaxError(f"missing target after {token}")
            fd, operator = redirect_ops[token]
            command.redirects.append(Redirect(fd, operator, tokens[index + 1]))
            index += 2
            continue
        command.argv.append(token)
        index += 1

    if not command.argv:
        raise ShellSyntaxError("empty command in pipeline")
    pipeline.append(command)
    return pipeline


def command_path(name: str) -> str | None:
    """Return the executable path found through the current PATH."""

    return which(name, path=os.environ.get("PATH"))


def builtin_type(name: str, out: TextIO) -> int:
    if name in BUILTINS:
        print(f"{name} is a shell builtin", file=out)
        return 0
    path = command_path(name)
    if path:
        print(f"{name} is {path}", file=out)
        return 0
    print(f"{name}: not found", file=out)
    return 1


def execute_builtin(argv: list[str], out: TextIO, err: TextIO) -> int:
    """Execute a built-in in the current process context."""

    name = argv[0]
    args = argv[1:]

    if name == "exit":
        if len(args) > 1:
            print("exit: too many arguments", file=err)
            return 1
        try:
            status = int(args[0]) if args else 0
        except ValueError:
            print(f"exit: {args[0]}: numeric argument required", file=err)
            status = 2
        raise ExitShell(status & 0xFF)

    if name == "echo":
        newline = True
        if args and args[0] == "-n":
            newline = False
            args = args[1:]
        print(" ".join(args), end="\n" if newline else "", file=out)
        return 0

    if name == "type":
        if not args:
            return 0
        status = 0
        for item in args:
            status = max(status, builtin_type(item, out))
        return status

    if name == "pwd":
        print(os.getcwd(), file=out)
        return 0

    if name == "cd":
        if len(args) > 1:
            print("cd: too many arguments", file=err)
            return 1
        destination = args[0] if args else os.environ.get("HOME")
        if not destination:
            print("cd: HOME is not set", file=err)
            return 1
        destination = os.path.expanduser(destination)
        try:
            old = os.getcwd()
            os.chdir(destination)
            os.environ["OLDPWD"] = old
            os.environ["PWD"] = os.getcwd()
        except OSError as exc:
            print(f"cd: {destination}: {exc.strerror}", file=err)
            return 1
        return 0

    if name == "export":
        status = 0
        for assignment in args:
            if "=" not in assignment:
                print(f"export: {assignment}: invalid assignment", file=err)
                status = 1
                continue
            variable, value = assignment.split("=", 1)
            if not VARIABLE_NAME.fullmatch(variable):
                print(f"export: {assignment}: invalid assignment", file=err)
                status = 1
                continue
            os.environ[variable] = value
        return status

    if name == "unset":
        status = 0
        for variable in args:
            if not VARIABLE_NAME.fullmatch(variable):
                print(f"unset: {variable}: invalid name", file=err)
                status = 1
                continue
            os.environ.pop(variable, None)
        return status

    if name == "help":
        print("Builtins: " + ", ".join(sorted(BUILTINS)), file=out)
        return 0

    print(f"{name}: unsupported builtin", file=err)
    return 1


def apply_redirects(redirects: list[Redirect]) -> list[int]:
    """Apply redirects to the process and return fds that should be closed."""

    opened: list[int] = []
    for redirect in redirects:
        if redirect.operator == "<":
            fd = os.open(redirect.target, os.O_RDONLY)
        elif redirect.operator == ">>":
            fd = os.open(redirect.target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        else:
            fd = os.open(redirect.target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        opened.append(fd)
        os.dup2(fd, redirect.fd)
        os.close(fd)
    return opened


def run_builtin_parent(command: SimpleCommand) -> int:
    """Run a state-changing builtin while preserving the shell's stdio."""

    saved = [os.dup(fd) for fd in (0, 1, 2)]
    try:
        apply_redirects(command.redirects)
        return execute_builtin(command.argv, sys.stdout, sys.stderr)
    except OSError as exc:
        print(f"pysh: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for fd, original in zip((0, 1, 2), saved):
            os.dup2(original, fd)
            os.close(original)


def run_pipeline(commands: list[SimpleCommand]) -> int:
    """Fork a process for each command and return the last status."""

    children: list[int] = []
    previous_read: int | None = None

    for index, command in enumerate(commands):
        next_read: int | None = None
        next_write: int | None = None
        if index < len(commands) - 1:
            next_read, next_write = os.pipe()

        pid = os.fork()
        if pid == 0:
            try:
                if previous_read is not None:
                    os.dup2(previous_read, 0)
                if next_write is not None:
                    os.dup2(next_write, 1)
                for fd in (previous_read, next_read, next_write):
                    if fd is not None:
                        try:
                            os.close(fd)
                        except OSError:
                            pass

                apply_redirects(command.redirects)
                if command.argv[0] in BUILTINS:
                    status = execute_builtin(command.argv, sys.stdout, sys.stderr)
                else:
                    executable = command_path(command.argv[0])
                    if not executable:
                        print(f"{command.argv[0]}: command not found", file=sys.stderr)
                        status = 127
                    else:
                        os.execvpe(executable, command.argv, os.environ.copy())
                        status = 127
            except ExitShell as exc:
                status = exc.status
            except OSError as exc:
                print(f"pysh: {exc}", file=sys.stderr)
                status = 1
            except BrokenPipeError:
                status = 1
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(status & 0xFF)

        children.append(pid)
        if previous_read is not None:
            os.close(previous_read)
        if next_write is not None:
            os.close(next_write)
        previous_read = next_read

    if previous_read is not None:
        os.close(previous_read)

    statuses: list[int] = []
    for child in children:
        _, status = os.waitpid(child, 0)
        if os.WIFEXITED(status):
            statuses.append(os.WEXITSTATUS(status))
        elif os.WIFSIGNALED(status):
            statuses.append(128 + os.WTERMSIG(status))
        else:
            statuses.append(1)
    return statuses[-1] if statuses else 0


def run_command(commands: list[SimpleCommand]) -> int:
    if not commands:
        return 0
    if len(commands) == 1 and commands[0].argv[0] in {"cd", "export", "unset"}:
        return run_builtin_parent(commands[0])
    return run_pipeline(commands)


def main() -> int:
    last_status = 0
    while True:
        try:
            sys.stdout.write("$ ")
            sys.stdout.flush()
            line = input()
        except EOFError:
            sys.stdout.write("\n")
            break
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            last_status = 130
            continue

        try:
            commands = parse(line, last_status)
            last_status = run_command(commands)
        except ShellSyntaxError as exc:
            print(f"pysh: syntax error: {exc}", file=sys.stderr)
            last_status = 2
        except ExitShell as exc:
            return exc.status

    return last_status


if __name__ == "__main__":
    raise SystemExit(main())