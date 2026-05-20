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
    has_chars = False  # Track if we've seen characters (to handle empty quotes '')

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
                # Peek ahead inside double quotes
                if i + 1 < len(command_str) and command_str[i + 1] in ('"', '\\', '$', '`'):
                    current_arg.append(command_str[i + 1])
                    has_chars = True
                    i += 1  # Skip the next character as it's escaped
                else:
                    current_arg.append(char)
                    has_chars = True
            else:
                current_arg.append(char)
                has_chars = True
        else:
            # Outside of any quotes
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

        # Step 1: Parse the command string completely into raw argument tokens
        raw_parts = parse_command(user_input)
        if not raw_parts:
            continue

        # Step 2: Extract redirection configuration if present
        parts = []
        output_file = None
        
        i = 0
        while i < len(raw_parts):
            if raw_parts[i] in (">", "1>"):
                if i + 1 < len(raw_parts):
                    output_file = raw_parts[i + 1]
                    i += 2  # Skip both the operator and the filename
                    continue
            parts.append(raw_parts[i])
            i += 1

        if not parts:
            continue

        command_name = parts[0]

        # Intercept stdout if a redirection file was captured
        original_stdout = sys.stdout
        file_handle = None

        if output_file:
            try:
                # Open in write mode: creates file or overwrites it
                file_handle = open(output_file, "w")
            except Exception as e:
                sys.stderr.write(f"shell: {output_file}: {e}\n")
                continue

        # Helper to route printing seamlessly for builtins
        def shell_print(*args, **kwargs):
            if file_handle:
                print(*args, file=file_handle, **kwargs)
            else:
                print(*args, **kwargs)

        # Handle Builtin Commands
        if command_name == "exit":
            if file_handle:
                file_handle.close()
            sys.exit(0)

        elif command_name == "echo":
            shell_print(" ".join(parts[1:]))
            if file_handle:
                file_handle.close()
            continue

        elif command_name == "pwd":
            shell_print(os.getcwd())
            if file_handle:
                file_handle.close()
            continue

        elif command_name == "cd":
            target_directory = parts[1] if len(parts) > 1 else "~"
            if target_directory == "~":
                target_directory = os.environ.get("HOME", "")
            
            if os.path.isdir(target_directory):
                os.chdir(target_directory)
            else:
                # Errors go directly to stderr, never redirected to the output file
                sys.stderr.write(f"cd: {parts[1]}: No such file or directory\n")
            
            if file_handle:
                file_handle.close()
            continue

        elif command_name == "type":
            if len(parts) < 2:
                if file_handle:
                    file_handle.close()
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
            
            if file_handle:
                file_handle.close()
            continue

        # Handle External Executables
        found_path = find_executable(command_name)
        if found_path:
            try:
                if file_handle:
                    # Pass the file handle directly to standard output stream of the child process
                    subprocess.run(
                        [command_name] + parts[1:], 
                        executable=found_path, 
                        stdout=file_handle
                    )
                else:
                    subprocess.run(
                        [command_name] + parts[1:], 
                        executable=found_path
                    )
            except Exception as e:
                sys.stderr.write(f"shell: execution error: {e}\n")
        else:
            sys.stderr.write(f"{command_name}: command not found\n")

        if file_handle:
            file_handle.close()

if __name__ == "__main__":
    main()
