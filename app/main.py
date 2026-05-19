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


def parse_command(command_str):
    """
    Parses a command string into arguments, handling single quotes,
    double quotes, and backslashes (both inside and outside double quotes).
    """
    args = []
    current_arg = ""
    in_single_quotes = False
    in_double_quotes = False
    is_escaped = False  # Track backslash escaping state outside quotes
    has_chars = False   # Track if we've accumulated characters for the current argument

    # We use a while loop with an index to manually peek at the next character when needed
    i = 0
    while i < len(command_str):
        char = command_str[i]

        if is_escaped:
            # Character following a backslash outside quotes is treated literally
            current_arg += char
            has_chars = True
            is_escaped = False
        elif in_single_quotes:
            if char == "'":
                in_single_quotes = False
                has_chars = True
            else:
                current_arg += char
                has_chars = True
        elif in_double_quotes:
            if char == "\\":
                # Peek at the next character to check if it's an escapable character
                if i + 1 < len(command_str) and command_str[i + 1] in ('"', '\\', '$', '`'):
                    # Consume the next character literally and skip the backslash
                    current_arg += command_str[i + 1]
                    has_chars = True
                    i += 1  # Skip the next character since we processed it here
                else:
                    # Treat the backslash literally if it doesn't precede an escapable character
                    current_arg += char
                    has_chars = True
            elif char == '"':
                in_double_quotes = False
                has_chars = True
            else:
                current_arg += char
                has_chars = True
        else:
            if char == "\\":
                is_escaped = True
            elif char == "'":
                in_single_quotes = True
            elif char == '"':
                in_double_quotes = True
            elif char.isspace():
                if has_chars:
                    args.append(current_arg)
                    current_arg = ""
                    has_chars = False
            else:
                current_arg += char
                has_chars = True
        
        i += 1

    # Append the last argument if there is one remaining
    if has_chars:
        args.append(current_arg)

    return args


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

        # Use our updated custom parser
        parts = parse_command(command)
        if not parts:
            continue
            
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
                
                # Check if the target is the home directory shorthand
                if target_directory == "~":
                    target_directory = os.environ.get("HOME", "")
                
                # Check if the directory exists on the filesystem
                if os.path.isdir(target_directory):
                    os.chdir(target_directory)
                else:
                    print(f"cd: {parts[1]}: No such file or directory")
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
