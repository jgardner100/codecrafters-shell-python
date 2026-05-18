import os
import subprocess
import sys


def find_executable(command_name):
    """
    Searches the PATH environment variable for an executable file.
    Returns the absolute path if found and executable, otherwise None.
    """
    path_env = os.environ.get("PATH", "")
    directories = path_env.split(os.pathsep)
    
    for directory in directories:
        full_path = os.path.join(directory, command_name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path
            
    return None


def main():
    # Keep track of the shell builtins supported so far
    BUILTINS = {"exit", "echo", "type", "pwd", "cd"}

    while True:
        sys.stdout.write("$ ")
        sys.stdout.flush()

        try:
            command = input()
        except EOFError:
            break

        command = command.strip()
        if not command:
            continue

        parts = command.split()
        command_name = parts[0]

        # Handle Builtin: exit
        if command_name == "exit":
            return

        # Handle Builtin: echo
        if command_name == "echo":
            print(" ".join(parts[1:]))
            continue

        # Handle Builtin: pwd
        if command_name == "pwd":
            print(os.getcwd())
            continue

        # Handle Builtin: cd
        if command_name == "cd":
            if len(parts) > 1:
                target_directory = parts[1]
                # Check if the directory exists on the filesystem
                if os.path.isdir(target_directory):
                    os.chdir(target_directory)
                else:
                    print(f"cd: {target_directory}: No such file or directory")
            continue

        # Handle Builtin: type
        if command_name == "type":
            if len(parts) > 1:
                target_command = parts[1]
                
                if target_command in BUILTINS:
                    print(f"{target_command} is a shell builtin")
                else:
                    found_path = find_executable(target_command)
                    if found_path:
                        print(f"{target_command} is {found_path}")
                    else:
                        print(f"{target_command}: not found")
            continue

        # Handle External Programs
        found_path = find_executable(command_name)
        if found_path:
            subprocess.run([command_name] + parts[1:], executable=found_path)
            continue

        # Fallback if command is neither a builtin nor an external program
        print(f"{command_name}: command not found")


if __name__ == "__main__":
    main()
