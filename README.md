# 🐍 PySh (Python Shell)

[![CodeCrafters Challenge](https://img.shields.io/badge/CodeCrafters-Build_Your_Own_Shell-blue?logo=github)](https://app.codecrafters.io/courses/shell/overview)
[![Language](https://img.shields.io/badge/Language-Python_3.x-yellow?logo=python&logoColor=white)](https://www.python.org/)

**PySh** is a lightweight, POSIX-compliant shell written entirely in Python. Originally started as part of the [CodeCrafters "Build Your Own Shell" Challenge](https://app.codecrafters.io/courses/shell/overview), this project serves as an educational deep dive into the inner workings of command-line interpreters. It demonstrates core shell functionalities from managing a Read-Eval-Print Loop (REPL) to argument parsing and system process execution.

---

## ✨ Key Features

- **REPL (Read-Eval-Print Loop)**: An interactive command-line interface with a custom `$` prompt.
- **Built-in Commands**:
  - `echo`: Prints text and arguments to the standard output.
  - `exit`: Terminates the shell session gracefully.
  - `type`: Identifies whether a command is a shell built-in or an executable located within the system's `$PATH`.
- **Execution Engine**: Discovers and executes external programs by dynamically searching the directories specified in the `$PATH` environment variable.
- **Output Redirection**: Foundational logic for redirecting standard output using the `>` operator (currently under active development).
- **Graceful Error Handling**: Detects and reports unrecognizable commands or missing executables.

---

## 🚀 Getting Started

### Prerequisites
Ensure you have the following installed on your system:
- [Python 3.x](https://www.python.org/)
- [uv](https://github.com/astral-sh/uv) (Optional, for dependency management)

### Running the Shell
To launch the interactive PySh environment, you can run the provided runner script:

```bash
./your_program.sh
```

Alternatively, you can execute the Python module directly:

```bash
python3 -m app.main
```

---

## 🛠️ Architecture Overview

- `app/main.py`: The core engine of the shell. It manages the infinite event loop, reads user input, and routes commands to their respective handlers.
- **Command Parsing**: Includes rudimentary parsing logic to split input strings, handling command names, arguments, and special operators.
- **Subprocess Management**: Leverages Python's built-in `subprocess` and `os` modules to fork processes and execute system-level binaries directly.

---

## 🏗️ Future Roadmap

- [ ] Complete implementation of output redirection operators (`>`, `>>`, `2>`).
- [ ] Environment variable management and expansion (e.g., `echo $USER`).
- [ ] Command history tracking (up/down arrow keys).
- [ ] Press `Tab` for command autocompletion.
- [ ] Support for command pipelines (`|`).
- [ ] Implementation of `cd` and `pwd` built-in commands for directory navigation.

---

## 🤝 Contributing

This project is a personal implementation of the [CodeCrafters Challenge](https://codecrafters.io). While it is primarily an educational undertaking, suggestions, forks, and code reviews are entirely welcome! Feel free to explore the codebase and propose enhancements.
