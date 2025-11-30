import sys


def main():
    while True:
        sys.stdout.write("$ ")
        command = input()
        if command == 'exit':
             break
        elif command[0:4] == 'echo':
             stringa = command.removeprefix('echo')
             stringa = stringa.strip()
             print(stringa)
        else:
            print(f"{command}: command not found")
        pass


if __name__ == "__main__":
        main()