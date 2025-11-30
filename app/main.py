import sys
import os
import subprocess

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
            path = os.environ.get('PATH','')
            directories = path.split(':')
            cmd_parts = command.split()
            cmd_name = cmd_parts[0]
            found = False
            for directory in directories:
                 full_path = os.path.join(directory,cmd_name)
                 if os.path.isfile(full_path) and os.access(full_path,os.X_OK):
                      subprocess.run([full_path]+ cmd_parts[1:])
                      found = True
                      break
            print(f"{command}: command not found")
        pass
        

if __name__ == "__main__":
        main(commands)