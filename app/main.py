import sys
import os
import subprocess

BUILTINS = {"exit", "echo", "type", "pwd", "cd"}

def parse_command(command_str):
    """
    Parses the command string character-by-character to properly handle:
    - Single quotes, double quotes, and backslashes.
    - Token concatenation and space preservation.
    """
    args = []
    current_arg = []
    
    in_single_quotes = False
    in_double_quotes = False
    is_escaped = False
    has_chars = False  # Track if we've seen characters

    i = 0
    while i < len(command_str):
        char = command_str[i]

        if is_escaped:
            current_arg.append(char)
            is_escaped = False
            has_chars = True
            i += 1
            continue

        if in_single_quotes:
            if char == "'":
                in_single_quotes = False
            else:
                current_arg.append(char)
                has_chars = True
        elif in_double_quotes:
            if char == '"':
                in_double_quotes = False
            elif char == '\\':
                if i + 1 < len(command_str) and command_str[i + 1] in ('"', '\\', '$', '`'):
                    current_arg.append(command_str[i + 1])
                    has_chars = True
                    i += 1
                else:
                    current_arg.append(char)
                    has_chars = True
            else:
                current_arg.append(char)
                has_chars = True
        else:
            if char == '\\':
                is_escaped = True
            elif char == "'":
                in_single_quotes = True
            elif char == '"':
                in_double_quotes = True
            elif char in (' ', '\t'):
                if current_arg or has_chars:
                    args.append("".join(current_arg))
                    current_arg = []
                    has_chars = False
            else:
                current_arg.append(char)
                has_chars = True
        i += 1

    if current_arg or has_chars:
        args.append("".join(current_arg))

    return args

def find_executable(command_name):
    """Searches the PATH environment variable for an executable."""
    path_env = os.environ.get("PATH", "")
    for directory in path_env.split(os.pathsep):
        full_path = os.path.join(directory, command_name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None

def main():
    while True:
        sys.stdout.write("$ ")
        sys.stdout.flush()
        
        try:
            user_input = sys.stdin.readline()
            if not user_input:
                break
        except KeyboardInterrupt:
            print()
            continue

        user_input = user_input.strip()
        if not user_input:
            continue

        # Step 1: Parse the command string into raw argument tokens
        raw_parts = parse_command(user_input)
        if not raw_parts:
            continue

        # Step 2: Extract redirection configurations and determine open modes
        parts = []
        stdout_file = None
        stdout_mode = "w"  # Default to overwrite
        stderr_file = None
        
        i = 0
        while i < len(raw_parts):
            if raw_parts[i] in (">", "1>"):
                if i + 1 < len(raw_parts):
                    stdout_file = raw_parts[i + 1]
                    stdout_mode = "w"
                    i += 2
                    continue
            elif raw_parts[i] in (">>", "1>>"):
                if i + 1 < len(raw_parts):
                    stdout_file = raw_parts[i + 1]
                    stdout_mode = "a"  # Switch mode to APPEND
                    i += 2
                    continue
            elif raw_parts[i] == "2>":
                if i + 1 < len(raw_parts):
                    stderr_file = raw_parts[i + 1]
                    i += 2
                    continue
            parts.append(raw_parts[i])
            i += 1

        if not parts:
            continue

        command_name = parts[0]

        # Step 3: Open file handles securely using the configured modes
        stdout_handle = None
        stderr_handle = None

        try:
            if stdout_file:
                stdout_handle = open(stdout_file, stdout_mode)
            if stderr_file:
                stderr_handle = open(stderr_file, "w")
        except Exception as e:
            sys.stderr.write(f"shell: redirection open error: {e}\n")
            if stdout_handle: stdout_handle.close()
            if stderr_handle: stderr_handle.close()
            continue

        # Helper to route stdout printing seamlessly for builtins
        def shell_print(*args, **kwargs):
            if stdout_handle:
                print(*args, file=stdout_handle, **kwargs)
            else:
                print(*args, **kwargs)

        # Helper to route stderr printing seamlessly for builtins
        def shell_error(message):
            if stderr_handle:
                stderr_handle.write(message)
            else:
                sys.stderr.write(message)

        def close_handles():
            if stdout_handle:
                stdout_handle.close()
            if stderr_handle:
                stderr_handle.close()

        # Handle Builtin Commands
        if command_name == "exit":
            close_handles()
            sys.exit(0)

        elif command_name == "echo":
            shell_print(" ".join(parts[1:]))
            close_handles()
            continue

        elif command_name == "pwd":
            shell_print(os.getcwd())
            close_handles()
            continue

        elif command_name == "cd":
            target_directory = parts[1] if len(parts) > 1 else "~"
            if target_directory == "~":
                target_directory = os.environ.get("HOME", "")
            
            if os.path.isdir(target_directory):
                os.chdir(target_directory)
            else:
                shell_error(f"cd: {parts[1]}: No such file or directory\n")
            
            close_handles()
            continue

        elif command_name == "type":
            if len(parts) < 2:
                close_handles()
                continue
            
            target_command = parts[1]
            if target_command in BUILTINS:
                shell_print(f"{target_command} is a shell builtin")
            else:
                found_path = find_executable(target_command)
                if found_path:
                    shell_print(f"{target_command} is {found_path}")
                else:
                    shell_print(f"{target_command}: not found")
            
            close_handles()
            continue

        # Handle External Executables
        found_path = find_executable(command_name)
        if found_path:
            try:
                subprocess.run(
                    [command_name] + parts[1:], 
                    executable=found_path, 
                    stdout=stdout_handle,
                    stderr=stderr_handle
                )
            except Exception as e:
                shell_error(f"shell: execution error: {e}\n")
        else:
            shell_error(f"{command_name}: command not found\n")

        close_handles()

if __name__ == "__main__":
    main()
