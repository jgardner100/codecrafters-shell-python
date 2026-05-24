import sys
import os
import subprocess
import readline

BUILTINS = {"exit", "echo", "type", "pwd", "cd", "complete", "jobs"}
AUTOCOMPLETE_COMMANDS = ["echo", "exit"]

# In-memory storage mapping command names to their registered completion script paths
COMPLETIONS = {}
REMOVED_COMPLETIONS = set()

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
        candidate = result_prefix + entry

        if os.path.isdir(full_path):
            candidate += "/"
        else:
            candidate += " "

        matches.append(candidate)

    return sorted(matches)

def completer(text, state):
    """Complete command names in position 0, and file paths or custom scripts elsewhere."""
    line = readline.get_line_buffer()
    begidx = readline.get_begidx()
    endidx = readline.get_endidx()
    line_before_cursor = line[:endidx]

    # A trailing delimiter means the cursor is on a new/empty argument, not on
    # the command word.  Some readline/libedit builds report begidx as 0 here,
    # which made `git <TAB>` get treated as command completion and inserted
    # extra spaces after `complete -r git`.
    cursor_after_space = line_before_cursor.endswith((" ", "\t"))

    tokens = line.split()
    if tokens:
        first_word = tokens[0]
        in_argument_position = (
            line_before_cursor.strip() != ""
            and (cursor_after_space or begidx > 0 or len(tokens) > 1)
        )

        # Step 1: Use a programmable completion script when one is registered
        # for the command currently being completed.
        if in_argument_position and first_word in COMPLETIONS:
            script_path = COMPLETIONS[first_word]

            argv1 = first_word
            argv2 = text

            prefix_line = line[:begidx]
            prefix_tokens = prefix_line.split()
            argv3 = prefix_tokens[-1] if prefix_tokens else ""

            env_override = os.environ.copy()
            env_override["COMP_LINE"] = line
            env_override["COMP_POINT"] = str(endidx)

            try:
                result = subprocess.run(
                    [script_path, argv1, argv2, argv3],
                    capture_output=True,
                    text=True,
                    check=True,
                    env=env_override,
                )
                outputs = sorted(l.strip() for l in result.stdout.splitlines() if l.strip())

                if len(outputs) == 1:
                    matches = [outputs[0] + " "]
                else:
                    matches = outputs
            except Exception:
                matches = []

            if state < len(matches):
                return matches[state]
            return None

        # If a programmable completion was explicitly removed for this command,
        # do not fall back to filename completion for a brand-new empty argument.
        # This preserves the CodeCrafters expectation for `complete -r git` then
        # `git <TAB>`: the line stays as `git `.
        if in_argument_position and text == "" and first_word in REMOVED_COMPLETIONS:
            return None

    # Step 2: Fall back to built-in/executable completion only for the command
    # word. Otherwise, complete filesystem paths. For `ls <TAB>`, readline passes
    # an empty text value, and we must still return entries like `dog/`.
    if line[:begidx].strip() == "" and not cursor_after_space:
        matches = [match + " " for match in get_all_executable_matches(text)]
    else:
        matches = get_path_matches(text)

    if state < len(matches):
        return matches[state]
    return None

# Register the completer
readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

if hasattr(readline, "set_completion_append_character"):
    try:
        readline.set_completion_append_character("")
    except Exception:
        pass

if "libedit" in (readline.__doc__ or "").lower():
    try:
        readline.parse_and_bind("set add-suffix off")
    except Exception:
        pass

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

        run_in_background = False
        if parts and parts[-1] == "&":
            run_in_background = True
            parts = parts[:-1]

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

        elif command_name == "jobs":
            close_handles()
            continue

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

        # Handle Complete Builtin
        elif command_name == "complete":
            if len(parts) > 1:
                # --- complete -p <cmd> ---
                if parts[1] == "-p" and len(parts) > 2:
                    target_cmd = parts[2]
                    if target_cmd in COMPLETIONS:
                        script_path = COMPLETIONS[target_cmd]
                        shell_print(f"complete -C '{script_path}' {target_cmd}")
                    else:
                        shell_print(f"complete: {target_cmd}: no completion specification")
                
                # --- complete -r <cmd> (New Code) ---
                elif parts[1] == "-r" and len(parts) > 2:
                    target_cmd = parts[2]
                    # Remove the programmable completion and remember that this
                    # command was explicitly unregistered, so its empty argument
                    # completion does not fall back to filenames.
                    COMPLETIONS.pop(target_cmd, None)
                    REMOVED_COMPLETIONS.add(target_cmd)
                
                # --- complete -C <script> <cmd> ---
                elif parts[1] == "-C" and len(parts) > 3:
                    script_path = parts[2]
                    target_cmd = parts[3]
                    COMPLETIONS[target_cmd] = script_path
                    REMOVED_COMPLETIONS.discard(target_cmd)
                    
            close_handles()
            continue

        # Handle External Executables
        found_path = find_executable(command_name)
        if found_path:
            try:
                if run_in_background:
                    process = subprocess.Popen(
                        [command_name] + parts[1:],
                        executable=found_path,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                    )
                    shell_print(f"[1] {process.pid}")
                else:
                    subprocess.run(
                        [command_name] + parts[1:],
                        executable=found_path,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                    )
            except Exception as e:
                shell_error(f"shell: execution error: {e}\n")
        else:
            shell_error(f"{command_name}: command not found\n")

        close_handles()

if __name__ == "__main__":
    main()
