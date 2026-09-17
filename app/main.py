"""PySh: a small, educational POSIX-like shell.

The implementation intentionally stays compact, but keeps the shell split into
four understandable pieces: lexing, parsing, built-ins, and process execution.
It is not intended to replace a full POSIX shell; it implements the features
documented by this project and the CodeCrafters shell stages.
"""

from __future__ import annotations

import atexit
import glob
import os
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import TextIO

try:
    import readline
except ImportError:  # pragma: no cover - readline is platform dependent.
    readline = None


BUILTINS = {
    "cd",
    "echo",
    "exit",
    "export",
    "help",
    "jobs",
    "fg",
    "bg",
    "wait",
    "pwd",
    "type",
    "unset",
}

VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
IFS_PATTERN = re.compile(r"[ \t\n]+")
HISTORY_LIMIT = 1000
LAST_BACKGROUND_PID = 0


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


@dataclass
class Job:
    job_id: int
    pids: list[int]
    pgid: int
    command: str
    state: str = "Running"
    statuses: dict[int, int] | None = None
    notified: bool = False

    def __post_init__(self) -> None:
        if self.statuses is None:
            self.statuses = {}


JOBS: dict[int, Job] = {}
NEXT_JOB_ID = 1


def _expand_parameter_at(text: str, index: int, last_status: int) -> tuple[str, int]:
    """Expand one parameter beginning at ``index`` and return value/new index."""

    global LAST_BACKGROUND_PID

    if index + 1 >= len(text):
        return "$", index + 1

    marker = text[index + 1]
    if marker == "?":
        return str(last_status), index + 2
    if marker == "$":
        return str(os.getpid()), index + 2
    if marker == "!":
        return str(LAST_BACKGROUND_PID), index + 2
    if marker == "#":
        return "0", index + 2
    if marker == "0":
        return sys.argv[0], index + 2

    if marker == "{":
        closing = text.find("}", index + 2)
        if closing == -1:
            return "$", index + 1
        expression = text[index + 2 : closing]
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)(?:(:-|:=|-|\+|:\+)(.*))?",
            expression,
        )
        if not match:
            return "", closing + 1
        name, operator, alternate = match.groups()
        value = os.environ.get(name)
        is_set = value is not None
        is_non_empty = bool(value)
        alternate_value = expand_variables(alternate or "", last_status)
        if operator in (":-", "-") and (not is_set or (operator == ":-" and not is_non_empty)):
            return alternate_value, closing + 1
        if operator in (":+", "+") and (is_set and (operator == "+" or is_non_empty)):
            return alternate_value, closing + 1
        if operator in (":=", "=") and (not is_set or (operator == ":=" and not is_non_empty)):
            os.environ[name] = alternate_value
            return alternate_value, closing + 1
        return value or "", closing + 1

    match = VARIABLE_NAME.match(text, index + 1)
    if match:
        return os.environ.get(match.group(0), ""), match.end()
    return "$", index + 1


def expand_variables(text: str, last_status: int) -> str:
    """Expand parameters, including POSIX-style default operators."""

    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "$":
            value, index = _expand_parameter_at(text, index, last_status)
            result.append(value)
        else:
            result.append(text[index])
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
    glob_active = False
    index = 0
    quote: str | None = None

    def flush() -> None:
        nonlocal glob_active, token_started
        if token_started:
            word = "".join(current)
            matches = sorted(glob.glob(word)) if glob_active and glob.has_magic(word) else []
            tokens.extend(matches or [word])
            current.clear()
            glob_active = False
            token_started = False

    def append_literal(value: str, allow_glob: bool = False) -> None:
        nonlocal glob_active, token_started
        current.extend(value)
        token_started = True
        if allow_glob and glob.has_magic(value):
            glob_active = True

    def append_expansion(value: str, quoted: bool) -> None:
        if quoted:
            append_literal(value)
            return
        fields = [field for field in IFS_PATTERN.split(value) if field]
        if not fields:
            return
        append_literal(fields[0])
        for field in fields[1:]:
            flush()
            append_literal(field)

    while index < len(line):
        char = line[index]

        if quote == "'":
            if char == "'":
                quote = None
            else:
                append_literal(char)
            index += 1
            continue

        if quote == '"':
            if char == '"':
                quote = None
                index += 1
                continue
            if char == "\\" and index + 1 < len(line) and line[index + 1] in '\\"$':
                append_literal(line[index + 1])
                index += 2
                continue
            if char == "$":
                value, index = _expand_parameter_at(line, index, last_status)
                append_expansion(value, quoted=True)
                continue
            append_literal(char)
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
                append_literal(line[index + 1])
                index += 2
            else:
                append_literal("\\")
                index += 1
            continue
        if char == "#":
            if not token_started:
                break
            append_literal(char)
            index += 1
            continue

        if char == "~" and not token_started and (index + 1 == len(line) or line[index + 1] == "/"):
            append_literal(os.environ.get("HOME", "~"))
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
        if char in "|<&":
            flush()
            tokens.append(char)
            index += 1
            continue
        if char == "$":
            value, index = _expand_parameter_at(line, index, last_status)
            append_expansion(value, quoted=False)
            continue

        append_literal(char, allow_glob=char in "*?[")
        index += 1

    if quote is not None:
        raise ShellSyntaxError("unterminated quote")
    flush()
    return tokens


def parse_job(line: str, last_status: int = 0) -> tuple[list[SimpleCommand], bool]:
    """Parse one line and return its pipeline plus background flag."""

    tokens = lex(line, last_status)
    if not tokens:
        return [], False

    background = tokens[-1] == "&"
    if background:
        tokens.pop()
        if not tokens:
            raise ShellSyntaxError("missing command before &")
    elif "&" in tokens:
        raise ShellSyntaxError("unexpected '&'")

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
    return pipeline, background


def parse(line: str, last_status: int = 0) -> list[SimpleCommand]:
    """Parse one line into a pipeline of simple commands.

    Kept as a small compatibility wrapper for callers that only need the
    foreground pipeline.
    """

    commands, _ = parse_job(line, last_status)
    return commands


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

    if name == "jobs":
        return jobs_builtin(out)

    if name == "fg":
        return foreground_builtin(args, out, err)

    if name == "bg":
        return background_builtin(args, err)

    if name == "wait":
        return wait_builtin(args, err)

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


def _status_from_wait(raw_status: int) -> int:
    if os.WIFEXITED(raw_status):
        return os.WEXITSTATUS(raw_status)
    if os.WIFSIGNALED(raw_status):
        return 128 + os.WTERMSIG(raw_status)
    return 1


def _reap_job(job: Job) -> None:
    """Collect any available child status without blocking."""

    assert job.statuses is not None
    for pid in job.pids:
        if pid in job.statuses:
            continue
        try:
            waited_pid, raw_status = os.waitpid(pid, os.WNOHANG | os.WUNTRACED | os.WCONTINUED)
        except ChildProcessError:
            job.statuses[pid] = 0
            continue
        if waited_pid == 0:
            continue
        if os.WIFSTOPPED(raw_status):
            job.state = "Stopped"
        elif os.WIFCONTINUED(raw_status):
            job.state = "Running"
        else:
            job.statuses[pid] = _status_from_wait(raw_status)

    if len(job.statuses) == len(job.pids):
        job.state = "Done"


def reap_jobs(announce: bool = False) -> None:
    for job in JOBS.values():
        previous_state = job.state
        _reap_job(job)
        if announce and previous_state == "Running" and job.state == "Done" and not job.notified:
            print(f"\n[{job.job_id}] Done {job.command}")
            job.notified = True


def _wait_for_job(job: Job) -> int:
    """Wait for every process in a job and return the last process status."""

    assert job.statuses is not None
    for pid in job.pids:
        if pid in job.statuses:
            continue
        while True:
            try:
                waited_pid, raw_status = os.waitpid(pid, os.WUNTRACED)
            except ChildProcessError:
                job.statuses[pid] = 0
                break
            if waited_pid != pid:
                continue
            if os.WIFSTOPPED(raw_status):
                job.state = "Stopped"
                break
            job.statuses[pid] = _status_from_wait(raw_status)
            break
    if len(job.statuses) == len(job.pids):
        job.state = "Done"
    return job.statuses.get(job.pids[-1], 1)


def _job_from_argument(args: list[str], err: TextIO) -> Job | None:
    if not JOBS:
        print("pysh: no current jobs", file=err)
        return None
    if not args:
        return JOBS[sorted(JOBS)[-1]]
    value = args[0][1:] if args[0].startswith("%") else args[0]
    try:
        job_id = int(value)
    except ValueError:
        print(f"pysh: {args[0]}: invalid job", file=err)
        return None
    job = JOBS.get(job_id)
    if job is None:
        print(f"pysh: {args[0]}: no such job", file=err)
    return job


def jobs_builtin(out: TextIO) -> int:
    reap_jobs()
    for job_id in sorted(JOBS):
        job = JOBS[job_id]
        print(f"[{job.job_id}] {job.state:<7} {job.command}", file=out)
    return 0


def foreground_builtin(args: list[str], out: TextIO, err: TextIO) -> int:
    job = _job_from_argument(args, err)
    if job is None:
        return 1
    if job.state == "Done":
        return job.statuses.get(job.pids[-1], 0) if job.statuses else 0
    try:
        if job.state == "Stopped":
            os.killpg(job.pgid, signal.SIGCONT)
            job.state = "Running"
    except ProcessLookupError:
        pass
    print(job.command, file=out)
    status = _wait_for_job(job)
    if job.state == "Done":
        JOBS.pop(job.job_id, None)
    return status


def background_builtin(args: list[str], err: TextIO) -> int:
    job = _job_from_argument(args, err)
    if job is None:
        return 1
    if job.state == "Done":
        return job.statuses.get(job.pids[-1], 0) if job.statuses else 0
    try:
        os.killpg(job.pgid, signal.SIGCONT)
        job.state = "Running"
        job.notified = False
        print(f"[{job.job_id}] {job.command}")
        return 0
    except ProcessLookupError:
        print(f"pysh: job {job.job_id} is no longer running", file=err)
        return 1


def wait_builtin(args: list[str], err: TextIO) -> int:
    if args:
        jobs = [_job_from_argument([argument], err) for argument in args]
        jobs = [job for job in jobs if job is not None]
    else:
        jobs = list(JOBS.values())
    status = 0
    for job in jobs:
        status = _wait_for_job(job)
        if job.state == "Done":
            JOBS.pop(job.job_id, None)
    return status


def _spawn_pipeline(commands: list[SimpleCommand]) -> tuple[list[int], int]:
    """Fork a pipeline and return its child PIDs and process group ID."""

    children: list[int] = []
    previous_read: int | None = None
    pgid: int | None = None

    for index, command in enumerate(commands):
        next_read: int | None = None
        next_write: int | None = None
        if index < len(commands) - 1:
            next_read, next_write = os.pipe()

        pid = os.fork()
        if pid == 0:
            try:
                os.setpgid(0, pgid or 0)
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
        if pgid is None:
            pgid = pid
        try:
            os.setpgid(pid, pgid)
        except OSError:
            pass
        if previous_read is not None:
            os.close(previous_read)
        if next_write is not None:
            os.close(next_write)
        previous_read = next_read

    if previous_read is not None:
        os.close(previous_read)
    return children, pgid or 0


def run_pipeline(
    commands: list[SimpleCommand],
    command_text: str = "",
    background: bool = False,
) -> int:
    """Run a pipeline in the foreground or register it as a background job."""

    global LAST_BACKGROUND_PID, NEXT_JOB_ID
    children, pgid = _spawn_pipeline(commands)
    if background:
        job_id = NEXT_JOB_ID
        NEXT_JOB_ID += 1
        JOBS[job_id] = Job(job_id, children, pgid, command_text or commands[0].argv[0])
        LAST_BACKGROUND_PID = children[-1]
        print(f"[{job_id}] {children[-1]}")
        return 0

    job = Job(0, children, pgid, command_text)
    return _wait_for_job(job)

def run_command(
    commands: list[SimpleCommand],
    command_text: str = "",
    background: bool = False,
) -> int:
    if not commands:
        return 0
    parent_builtins = {"cd", "export", "unset", "jobs", "fg", "bg", "wait"}
    if not background and len(commands) == 1 and commands[0].argv[0] in parent_builtins:
        return run_builtin_parent(commands[0])
    return run_pipeline(commands, command_text, background)


_completion_matches: list[str] = []
_completion_prefix = ""


def _completion_candidates(text: str, line: str, begin: int) -> list[str]:
    if begin == 0 or not line[:begin].strip():
        candidates = set(BUILTINS)
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                directory = "."
            try:
                candidates.update(
                    entry.name
                    for entry in Path(directory).iterdir()
                    if entry.is_file() and os.access(entry, os.X_OK)
                )
            except OSError:
                continue
        return sorted(candidate for candidate in candidates if candidate.startswith(text))

    expanded = os.path.expanduser(text)
    directory, prefix = os.path.split(expanded)
    directory = directory or "."
    try:
        entries = sorted(Path(directory).iterdir())
    except OSError:
        return []
    matches: list[str] = []
    for entry in entries:
        if not entry.name.startswith(prefix):
            continue
        candidate = str(Path(directory, entry.name))
        if entry.is_dir():
            candidate += "/"
        if text.startswith("~"):
            home = str(Path.home())
            candidate = candidate.replace(home, "~", 1)
        matches.append(candidate)
    return matches


def complete(text: str, state: int) -> str | None:
    """Readline callback for commands and filesystem paths."""

    global _completion_matches, _completion_prefix
    if readline is None:
        return None
    line = readline.get_line_buffer()
    begin = readline.get_begidx()
    if state == 0 or text != _completion_prefix:
        _completion_prefix = text
        _completion_matches = _completion_candidates(text, line, begin)
    return _completion_matches[state] if state < len(_completion_matches) else None


def configure_line_editor() -> None:
    """Enable persistent history and tab completion when readline is present."""

    if readline is None or not sys.stdin.isatty():
        return
    history_path = Path(os.environ.get("PYSH_HISTORY_FILE", Path.home() / ".pysh_history"))
    try:
        readline.read_history_file(str(history_path))
    except OSError:
        pass
    readline.set_history_length(HISTORY_LIMIT)
    readline.set_completer(complete)
    readline.parse_and_bind("tab: complete")

    def save_history() -> None:
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(str(history_path))
        except OSError:
            pass

    atexit.register(save_history)


def configure_job_control() -> None:
    """Keep the interactive shell alive while jobs are stopped or resumed."""

    if not sys.stdin.isatty():
        return
    for signum in (signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU):
        signal.signal(signum, signal.SIG_IGN)


def main() -> int:
    last_status = 0
    configure_line_editor()
    configure_job_control()
    while True:
        reap_jobs(announce=True)
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
            if readline is not None and sys.stdin.isatty() and line.strip():
                readline.add_history(line)
            commands, background = parse_job(line, last_status)
            last_status = run_command(commands, line, background)
        except ShellSyntaxError as exc:
            print(f"pysh: syntax error: {exc}", file=sys.stderr)
            last_status = 2
        except ExitShell as exc:
            return exc.status

    return last_status


if __name__ == "__main__":
    raise SystemExit(main())