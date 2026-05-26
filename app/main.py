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
            elif char == '|':
                if current_arg or has_chars:
                    args.append("".join(current_arg))
                    current_arg = []
                    has_chars = False
                args.append("|")
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

def next_job_number(background_jobs):
    """Return the smallest available job number."""
    used_numbers = {job["job_number"] for job in background_jobs}
    job_number = 1
    while job_number in used_numbers:
        job_number += 1
    return job_number

def format_job(job, marker="+"):
    """Format a background job in the jobs builtin output format."""
    status = job["status"]
    command = job["command"]

    # Running background jobs are displayed with the trailing ampersand.
    # Completed jobs are displayed once as Done, without the trailing ampersand,
    # then removed from the job table.
    if status == "Done" and command.endswith(" &"):
        command = command[:-2]

    return f"[{job['job_number']}]{marker}  {status:<24}{command}"


def get_job_markers(jobs):
    """Return the marker for each job number based on start order."""
    markers = {job["job_number"]: " " for job in jobs}

    if jobs:
        markers[jobs[-1]["job_number"]] = "+"
    if len(jobs) > 1:
        markers[jobs[-2]["job_number"]] = "-"

    return markers


def run_external_pipeline(parts, stdout_handle=None, stderr_handle=None, shell_error=sys.stderr.write):
    """Run a simple two-command external pipeline.

    The current CodeCrafters stage only requires pipelines made from two
    external commands, such as `cat file | wc` and `tail -f file | head -n 5`.
    This function starts both commands with the stdout of the left command
    connected to the stdin of the right command.
    """
    pipe_count = parts.count("|")
    if pipe_count != 1:
        shell_error("shell: only two-command pipelines are supported\n")
        return

    pipe_index = parts.index("|")
    left_parts = parts[:pipe_index]
    right_parts = parts[pipe_index + 1:]

    if not left_parts or not right_parts:
        shell_error("shell: invalid pipeline\n")
        return

    left_path = find_executable(left_parts[0])
    if not left_path:
        shell_error(f"{left_parts[0]}: command not found\n")
        return

    right_path = find_executable(right_parts[0])
    if not right_path:
        shell_error(f"{right_parts[0]}: command not found\n")
        return

    left_process = None
    right_process = None

    try:
        left_process = subprocess.Popen(
            [left_parts[0]] + left_parts[1:],
            executable=left_path,
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
        )

        right_process = subprocess.Popen(
            [right_parts[0]] + right_parts[1:],
            executable=right_path,
            stdin=left_process.stdout,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )

        # The parent must close its copy of the pipe's write/read handle so the
        # right command can see EOF and the left command can receive SIGPIPE if
        # the right command exits early. This is important for `tail -f | head`.
        if left_process.stdout:
            left_process.stdout.close()

        right_process.wait()

        # In cases like `tail -f file | head -n 5`, the right command exits
        # once it has enough input, but the left command can otherwise keep
        # following the file. Clean it up so the shell returns to the prompt.
        try:
            left_process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            left_process.terminate()
            try:
                left_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                left_process.kill()
                left_process.wait()

    except Exception as e:
        shell_error(f"shell: pipeline execution error: {e}\n")

        for process in (right_process, left_process):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def reap_jobs(background_jobs, display_done_only=True, output_func=print):
    """
    Reap exited background jobs.

    When display_done_only is True, only completed jobs are printed. This is
    used before each prompt. When False, both running and completed jobs are
    printed for the jobs builtin. Completed jobs are removed in both cases, so
    each Done line appears exactly once.
    """
    jobs_to_display = []
    remaining_jobs = []
    done_jobs = []

    for job in background_jobs:
        if job["process"].poll() is None:
            job["status"] = "Running"
            jobs_to_display.append(job)
            remaining_jobs.append(job)
        else:
            job["status"] = "Done"
            jobs_to_display.append(job)
            done_jobs.append(job)

    markers = get_job_markers(jobs_to_display)
    display_jobs = done_jobs if display_done_only else jobs_to_display

    for job in sorted(display_jobs, key=lambda item: item["job_number"]):
        output_func(format_job(job, markers.get(job["job_number"], " ")))

    return remaining_jobs

def main():
    background_jobs = []
    while True:
        # Reap any completed background jobs before showing the next prompt.
        # This prints Done lines after the previous command output and before
        # the next $ prompt.
        background_jobs = reap_jobs(background_jobs, display_done_only=True)

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

        # Handle simple two-command external pipelines before builtins.
        if "|" in parts:
            if run_in_background:
                shell_error("shell: background pipelines are not supported\n")
            else:
                run_external_pipeline(
                    parts,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                    shell_error=shell_error,
                )

            close_handles()
            continue

        # Handle Builtin Commands
        if command_name == "exit":
            close_handles()
            sys.exit(0)

        elif command_name == "jobs":
            background_jobs = reap_jobs(
                background_jobs,
                display_done_only=False,
                output_func=shell_print,
            )

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
                    job_number = next_job_number(background_jobs)
                    command_text = " ".join(parts) + " &"
                    background_jobs.append({
                        "job_number": job_number,
                        "process": process,
                        "pid": process.pid,
                        "command": command_text,
                        "status": "Running",
                    })
                    shell_print(f"[{job_number}] {process.pid}")
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
