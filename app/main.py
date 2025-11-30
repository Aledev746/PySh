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
        elif command[0:4] == 'type':
             str1 = command.removeprefix('type')
             str1 = str1.strip()
             if str1 == 'echo' or str1 == 'exit' or str1 == 'type':
                  print(f'{str1} is a shell builtin')
        else:
            print(f"{command}: not found")
        pass


if __name__ == "__main__":
        main()