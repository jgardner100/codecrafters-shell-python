import sys
import os
import subprocess
import readline

BUILTINS = {"exit", "echo", "type", "pwd", "cd"}
AUTOCOMPLETE_COMMANDS = ["echo", "exit"]

def get_all_executable_matches(text):
    """
    Scans BUILTINS and all directories in PATH to find files starting with 'text'
    that are valid executable files. Returns a sorted list of unique matches.
    """
    matches = set()
    
    # 1. Check builtins
    for cmd in AUTOCOMPLETE_COMMANDS:
        if cmd.startswith(text):
            matches.add(cmd)
            
    # 2. Check executables in PATH
    path_env = os.environ.get("PATH", "")
    for directory in path_env.split(os.pathsep):
        if not directory or not os.path.isdir(directory):
            continue
        try:
            # List files in the directory
            for filename in os.listdir(directory):
                if filename.startswith(text):
                    full_path = os.path.join(directory, filename)
                    # Verify it's a file and executable
                    if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                        matches.add(filename)
        except Exception:
            # Handle unreadable or permission-denied directories gracefully
            continue
            
    return sorted(list(matches))

def get_path_matches(text):
    """
    Complete non-command words as filesystem paths.

    The value returned to readline must be the full replacement token,
    not only the missing suffix. For example, when text is "b" and
    the file is "bar", return "bar ", not "ar ".
    """
    if "/" in text:
        directory_part, filename_prefix = text.rsplit("/", 1)
        search_dir = directory_part if directory_part else "/"
        result_prefix = directory_part + "/"
    else:
        search_dir = "."
        filename_prefix = text
        result_prefix = ""

    try:
        entries = os.listdir(search_dir)
    except OSError:
        return []

    matches = []
    for entry in entries:
        if not entry.startswith(filename_prefix):
            continue

        full_path = os.path.join(search_dir, entry)

        # Return the complete word that should replace the current token.
        candidate = result_prefix + entry

        if os.path.isdir(full_path):
            candidate += "/"
        else:
            candidate += " "

        matches.append(candidate)

    return sorted(matches)


def completer(text, state):
    """Complete command names in position 0, and file paths elsewhere."""
    line = readline.get_line_buffer()
    begidx = readline.get_begidx()

    # If everything before the current token is whitespace, this is the
    # command word. Otherwise it is an argument and should use path completion.
    if line[:begidx].strip() == "":
        matches = [match + " " for match in get_all_executable_matches(text)]
    else:
        matches = get_path_matches(text)

    if state < len(matches):
        return matches[state]
    return None

# Register the completer
readline.set_completer(completer)

# Fallback bindings ensuring TAB works under GNU Readline as well as BSD Editline (libedit)
#readline.parse_and_bind("bind ^I rl_complete")
readline.parse_and_bind("tab: complete")

# Cross-platform safe configuration for appending trailing spaces
if hasattr(readline, "set_completion_append_character"):
    try:
        readline.set_completion_append_character("")
    except Exception:
        pass

# Safe libedit check via the module documentation string
if "libedit" in (readline.__doc__ or "").lower():
    try:
        readline.parse_and_bind("set add-suffix off")
    except Exception:
        pass

# Define delimiters so readline knows where words start and end
readline.set_completer_delims(" \t\n")

def parse_command(command_str):
    """Parses the command string character-by-character."""
    args = []
    current_arg = []
    
    in_single_quotes = False
    in_double_quotes = False
    is_escaped = False
    has_chars = False

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
        try:
            user_input = input("$ ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        raw_parts = parse_command(user_input)
        if not raw_parts:
            continue

        parts = []
        stdout_file = None
        stdout_mode = "w"
        stderr_file = None
        stderr_mode = "w"
        
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
                    stdout_mode = "a"
                    i += 2
                    continue
            elif raw_parts[i] == "2>":
                if i + 1 < len(raw_parts):
                    stderr_file = raw_parts[i + 1]
                    stderr_mode = "w"
                    i += 2
                    continue
            elif raw_parts[i] == "2>>":
                if i + 1 < len(raw_parts):
                    stderr_file = raw_parts[i + 1]
                    stderr_mode = "a"
                    i += 2
                    continue
            parts.append(raw_parts[i])
            i += 1

        if not parts:
            continue

        command_name = parts[0]

        stdout_handle = None
        stderr_handle = None

        try:
            if stdout_file:
                stdout_handle = open(stdout_file, stdout_mode)
            if stderr_file:
                stderr_handle = open(stderr_file, stderr_mode)
        except Exception as e:
            sys.stderr.write(f"shell: redirection open error: {e}\n")
            if stdout_handle: stdout_handle.close()
            if stderr_handle: stderr_handle.close()
            continue

        def shell_print(*args, **kwargs):
            if stdout_handle:
                print(*args, file=stdout_handle, **kwargs)
            else:
                print(*args, **kwargs)

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
