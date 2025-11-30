import sys

commands = ['exit','echo','type']
def main(commands):
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
            for cmd in commands:
                    if str1 == cmd:
                        print(f'{cmd} is a shell builtin')
            if str1 not in commands:
                 print(f'{str1}: not found')
                
        else:
            print(f"{command}: command not found")
        pass


if __name__ == "__main__":
        main(commands)