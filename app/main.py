import sys
import os
import subprocess
import readline
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Pipeline builtins patch: pipeline stages dispatch shell builtins before PATH lookup.
BUILTINS = {"exit", "echo", "type", "pwd", "cd", "complete", "jobs", "history"}
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
            pass
            
    return sorted(list(matches))

def completer(text, state):
    """
    Custom autocomplete callback matching text against builtins and path executables,
    or delegating to external custom completion scripts via `complete -C`.
    """
    buffer = readline.get_line_buffer()
    
    # Check if we are completing arguments for an external custom registered script
    tokens = []
    current_word = []
    in_quotes = False
    quote_char = None
    
    i = 0
    while i < len(buffer):
        c = buffer[i]
        if in_quotes:
            if c == quote_char:
                in_quotes = False
                quote_char = None
            else:
                current_word.append(c)
        else:
            if c in ("'", '"'):
                in_quotes = True
                quote_char = c
            elif c.isspace():
                if current_word:
                    tokens.append("".join(current_word))
                    current_word = []
            else:
                current_word.append(c)
        i += 1
    if current_word:
        tokens.append("".join(current_word))
        
    # Determine the context of completion
    is_arg_completion = False
    cmd_name = None
    if tokens:
        cmd_name = tokens[0]
        # If there are tokens, and the cursor position isn't within the first token
        if len(tokens) > 1 or (buffer and buffer[-1].isspace()):
            is_arg_completion = True

    if is_arg_completion and cmd_name in COMPLETIONS:
        if state == 0:
            script_path = COMPLETIONS[cmd_name]
            
            # Context details to pass down to target script:
            # argv[1] = command name
            # argv[2] = current word being completed
            # argv[3] = preceding word
            current_word_str = text
            prev_word_str = ""
            
            if buffer and buffer[-1].isspace():
                current_word_str = ""
                if tokens:
                    prev_word_str = tokens[-1]
            else:
                if len(tokens) >= 2:
                    prev_word_str = tokens[-2] if current_word_str else tokens[-1]
                    
            try:
                res = subprocess.run(
                    [script_path, cmd_name, current_word_str, prev_word_str],
                    capture_output=True,
                    text=True,
                    check=False
                )
                output = res.stdout.strip()
                if output:
                    completer.choices = [line.strip() + " " for line in output.splitlines() if line.strip()]
                else:
                    completer.choices = []
            except Exception:
                completer.choices = []
        
        if state < len(completer.choices):
            return completer.choices[state]
        return None

    # Fallback to default Builtins/Path executables matching logic
    if state == 0:
        all_matches = get_all_executable_matches(text)
        if all_matches:
            completer.choices = [match + " " for match in all_matches]
        else:
            completer.choices = []
            
    if state < len(completer.choices):
        return completer.choices[state]
        
    # If no options match, ring the terminal bell
    if state == 0 and not completer.choices:
        sys.stdout.write("\a")
        sys.stdout.flush()
    return None

# Configure readline autocompletion
readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

# Override default delimiters so full words including hyphens/slashes can be processed cleanly
try:
    readline.set_completer_delims(" \t\n")
except Exception:
    pass

# Force immediate auto-suffix behavior suppression safely depending on the dynamic engine platform
try:
    readline.parse_and_bind("set add-suffix off")
except Exception:
    pass

if "libedit" in getattr(readline, "__doc__", "").lower():
    try:
        readline.parse_and_bind("bind ^I rl_complete")
    except Exception:
        pass

def parse_command(command_str):
    """
    Parses a command string into tokens, preserving single and double quoted text
    and unescaped characters.
    """
    parts = []
    current_arg = []
    in_single_quotes = False
    in_double_quotes = False
    
    i = 0
    while i < len(command_str):
        char = command_str[i]
        
        if in_single_quotes:
            if char == "'":
                in_single_quotes = False
            else:
                current_arg.append(char)
        elif in_double_quotes:
            if char == '"':
                in_double_quotes = False
            elif char == '\\':
                if i + 1 < len(command_str):
                    next_char = command_str[i + 1]
                    if next_char in ('"', '\\', '$', '`'):
                        current_arg.append(next_char)
                        i += 1
                    else:
                        current_arg.append(char)
                else:
                    current_arg.append(char)
            else:
                current_arg.append(char)
        else:
            if char == "'":
                in_single_quotes = True
            elif char == '"':
                in_double_quotes = True
            elif char == '\\':
                if i + 1 < len(command_str):
                    current_arg.append(command_str[i + 1])
                    i += 1
            elif char.isspace():
                if current_arg:
                    parts.append("".join(current_arg))
                    current_arg = []
            else:
                current_arg.append(char)
        i += 1
        
    if current_arg:
        parts.append("".join(current_arg))
        
    return parts

def next_job_number(background_jobs):
    """Returns the next sequential tracking job number starting from 1."""
    if not background_jobs:
        return 1
    return max(job["job_number"] for job in background_jobs) + 1

def clean_completed_jobs(background_jobs):
    """Checks the statuses of current background processes, updates their states, and filters terminated ones."""
    for job in background_jobs:
        if job["status"] == "Running":
            poll = job["process"].poll()
            if poll is not None:
                job["status"] = "Done"

def iter_history_entries(command_history, parts):
    """
    Generates a filtered subset sequence of history tuples (index, command_text) 
    depending on slice configurations or numeric constraints.
    """
    history_len = len(command_history)
    limit = history_len
    
    if len(parts) > i_offset := 1:
        try:
            val = int(parts[i_offset])
            if val > 0:
                limit = min(val, history_len)
        except ValueError:
            pass
            
    start_idx = history_len - limit
    for idx in range(start_idx, history_len):
        yield (idx + 1, command_history[idx])

def run_builtin(command_name, parts, stdout_file, stderr_file, command_history=None, background_jobs=None):
    """
    Runs a shell builtin inside a separate redirected pipeline file descriptor context.
    Returns integer exit code.
    """
    def write_line(file_obj, text):
        file_obj.write(text + "\n")
        file_obj.flush()
        
    if command_name == "exit":
        sys.exit(0)
        
    elif command_name == "echo":
        write_line(stdout_file, " ".join(parts[1:]))
        return 0
        
    elif command_name == "type":
        if len(parts) > 1:
            target = parts[1]
            if target in BUILTINS:
                write_line(stdout_file, f"{target} is a shell builtin")
            else:
                found_path = find_executable(target)
                if found_path:
                    write_line(stdout_file, f"{target} is {found_path}")
                else:
                    write_line(stderr_file, f"sh: type: {target}: not found")
                    return 1
        return 0
        
    elif command_name == "pwd":
        write_line(stdout_file, os.getcwd())
        return 0
        
    elif command_name == "cd":
        if len(parts) > 1:
            target_directory = parts[1]
            if target_directory == "~":
                target_directory = os.environ.get("HOME", "")
            try:
                os.chdir(target_directory)
            except Exception:
                write_line(stderr_file, f"cd: {parts[1]}: No such file or directory")
                return 1
        return 0

    elif command_name == "complete":
        # complete command behavior logic validation fallback for pipeline stages
        return 0

    elif command_name == "jobs":
        if background_jobs is not None:
            clean_completed_jobs(background_jobs)
            for job in background_jobs:
                write_line(stdout_file, f"[{job['job_number']}] {job['pid']} {job['status']} \t {job['command']}")
            # Drop finished tracking markers cleanly
            background_jobs[:] = [j for j in background_jobs if j["status"] == "Running"]
        return 0

    elif command_name == "history":
        if command_history is not None:
            # Handle history -r inside pipeline fallback definitions
            if len(parts) > 2 and parts[1] == "-r":
                history_file = parts[2]
                try:
                    with open(history_file, "r") as f:
                        for line in f:
                            cleaned = line.strip()
                            if cleaned:
                                command_history.append(cleaned)
                except Exception:
                    pass
                return 0
                
            for index, command in iter_history_entries(command_history, parts):
                write_line(stdout_file, f"{index:5}  {command}")
        return 0
        
    return 1

def find_executable(command_name):
    """Locates an external command in the environment PATH."""
    path_env = os.environ.get("PATH", "")
    for directory in path_env.split(os.pathsep):
        full_path = os.path.join(directory, command_name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None

def parse_pipeline(command_str):
    """
    Parses a raw command string into a series of distinct pipeline stages,
    splitting safely on pipe characters '|' unless they are quoted or escaped.
    """
    stages = []
    current_stage = []
    in_single_quotes = False
    in_double_quotes = False
    
    i = 0
    while i < len(command_str):
        char = command_str[i]
        if in_single_quotes:
            if char == "'":
                in_single_quotes = False
            current_stage.append(char)
        elif in_double_quotes:
            if char == '"':
                in_double_quotes = False
            current_stage.append(char)
        else:
            if char == "'":
                in_single_quotes = True
                current_stage.append(char)
            elif char == '"':
                in_double_quotes = True
                current_stage.append(char)
            elif char == '\\':
                current_stage.append(char)
                if i + 1 < len(command_str):
                    current_stage.append(command_str[i+1])
                    i += 1
            elif char == '|':
                stages.append("".join(current_stage))
                current_stage = []
            else:
                current_stage.append(char)
        i += 1
        
    if current_stage:
        stages.append("".join(current_stage))
    return stages

def run_pipeline(stages, command_history, background_jobs):
    """
    Executes a structured command pipeline. Sets up input/output file descriptor 
    channels linking sequential commands together, handling redirection and builtins natively.
    """
    num_commands = len(stages)
    pipes = [os.pipe() for _ in range(num_commands - 1)]
    processes = []
    
    for idx, stage_str in enumerate(stages):
        # Extract individual stage redirection configuration rules
        raw_parts = parse_command(stage_str.strip())
        parts = []
        
        stdout_redirection_file = None
        stderr_redirection_file = None
        stdout_mode = "w"
        stderr_mode = "w"
        
        skip = False
        for i in range(len(raw_parts)):
            if skip:
                skip = False
                continue
                
            if raw_parts[i] in (">", "1>"):
                if i + 1 < len(raw_parts):
                    stdout_redirection_file = raw_parts[i+1]
                    stdout_mode = "w"
                    skip = True
            elif raw_parts[i] in (">>", "1>>"):
                if i + 1 < len(raw_parts):
                    stdout_redirection_file = raw_parts[i+1]
                    stdout_mode = "a"
                    skip = True
            elif raw_parts[i] == "2>":
                if i + 1 < len(raw_parts):
                    stderr_redirection_file = raw_parts[i+1]
                    stderr_mode = "w"
                    skip = True
            elif raw_parts[i] == "2>>":
                if i + 1 < len(raw_parts):
                    stderr_redirection_file = raw_parts[i+1]
                    stderr_mode = "a"
                    skip = True
            else:
                parts.append(raw_parts[i])
                
        if not parts:
            continue
            
        command_name = parts[0]
        
        # Fork target process stage
        pid = os.fork()
        if pid == 0:
            # CHILD PROCESS CONTEXT
            # Wire up stdin link descriptor
            if idx > 0:
                os.dup2(pipes[idx-1][0], sys.stdin.fileno())
            # Wire up stdout link descriptor
            if idx < num_commands - 1:
                os.dup2(pipes[idx][1], sys.stdout.fileno())
                
            # Close all copied pipe copies inside child frame context
            for p in pipes:
                os.close(p[0])
                os.close(p[1])
                
            # Set up file level streams redirections overrides
            if stdout_redirection_file:
                fd = os.open(stdout_redirection_file, os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if stdout_mode == "w" else os.O_APPEND), 0o644)
                os.dup2(fd, sys.stdout.fileno())
                os.close(fd)
                
            if stderr_redirection_file:
                fd = os.open(stderr_redirection_file, os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if stderr_mode == "w" else os.O_APPEND), 0o644)
                os.dup2(fd, sys.stderr.fileno())
                os.close(fd)
                
            # Process Execution Routing: Builtins vs Path Executables
            if command_name in BUILTINS:
                code = run_builtin(command_name, parts, sys.stdout, sys.stderr, command_history, background_jobs)
                sys.exit(code)
            else:
                found_path = find_executable(command_name)
                if found_path:
                    try:
                        os.execv(found_path, [command_name] + parts[1:])
                    except Exception as e:
                        sys.stderr.write(f"shell: execution error: {e}\n")
                        sys.exit(1)
                else:
                    sys.stderr.write(f"{command_name}: command not found\n")
                    sys.exit(127)
        else:
            # PARENT PROCESS CONTEXT
            processes.append(pid)
            
    # Close pipe resources in parent loop frame
    for p in pipes:
        os.close(p[0])
        os.close(p[1])
        
    # Wait for completion of all pipeline children stages
    for pid in processes:
        os.waitpid(pid, 0)

def main():
    command_history = []
    background_jobs = []
    
    while True:
        try:
            sys.stdout.write("$ ")
            sys.stdout.flush()
            
            command = sys.stdin.readline()
            if not command:
                break
                
            command_stripped = command.strip()
            if not command_stripped:
                continue
                
            command_history.append(command_stripped)
            
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            continue
        except Exception:
            break

        # Scan for sequential background operator tasks symbol tokens
        run_in_background = False
        if command_stripped.endswith("&"):
            run_in_background = True
            command_stripped = command_stripped[:-1].strip()

        # Route multi stage pipelines through custom execution subshell architecture
        pipeline_stages = parse_pipeline(command_stripped)
        if len(pipeline_stages) > 1:
            run_pipeline(pipeline_stages, command_history, background_jobs)
            continue

        # Single command parsing track
        raw_parts = parse_command(command_stripped)
        if not raw_parts:
            continue

        # Extract output redirection operators if specified
        parts = []
        stdout_file_path = None
        stderr_file_path = None
        stdout_mode = "w"
        stderr_mode = "w"

        skip = False
        for i in range(len(raw_parts)):
            if skip:
                skip = False
                continue
            if raw_parts[i] in (">", "1>"):
                if i + 1 < len(raw_parts):
                    stdout_file_path = raw_parts[i+1]
                    stdout_mode = "w"
                    skip = True
            elif raw_parts[i] in (">>", "1>>"):
                if i + 1 < len(raw_parts):
                    stdout_file_path = raw_parts[i+1]
                    stdout_mode = "a"
                    skip = True
            elif raw_parts[i] == "2>":
                if i + 1 < len(raw_parts):
                    stderr_file_path = raw_parts[i+1]
                    stderr_mode = "w"
                    skip = True
            elif raw_parts[i] == "2>>":
                if i + 1 < len(raw_parts):
                    stderr_file_path = raw_parts[i+1]
                    stderr_mode = "a"
                    skip = True
            else:
                parts.append(raw_parts[i])

        if not parts:
            continue

        command_name = parts[0]

        # Conditionally override file descriptors
        stdout_handle = sys.stdout
        stderr_handle = sys.stderr
        opened_stdout = None
        opened_stderr = None

        if stdout_file_path:
            opened_stdout = open(stdout_file_path, stdout_mode)
            stdout_handle = opened_stdout
        if stderr_file_path:
            opened_stderr = open(stderr_file_path, stderr_mode)
            stderr_handle = opened_stderr

        def shell_print(text):
            stdout_handle.write(text + "\n")
            stdout_handle.flush()

        def shell_error(text):
            stderr_handle.write(text)
            stderr_handle.flush()

        def close_handles():
            if opened_stdout:
                opened_stdout.close()
            if opened_stderr:
                opened_stderr.close()

        # Handle Internal Builtins
        if command_name == "exit":
            close_handles()
            sys.exit(0)
            
        elif command_name == "echo":
            shell_print(" ".join(parts[1:]))
            close_handles()
            continue
            
        elif command_name == "type":
            if len(parts) > 1:
                target = parts[1]
                if target in BUILTINS:
                    shell_print(f"{target} is a shell builtin")
                else:
                    found_path = find_executable(target)
                    if found_path:
                        shell_print(f"{target} is {found_path}")
                    else:
                        shell_error(f"sh: type: {target}: not found\n")
            close_handles()
            continue
            
        elif command_name == "pwd":
            shell_print(os.getcwd())
            close_handles()
            continue
            
        elif command_name == "cd":
            if len(parts) > 1:
                target_directory = parts[1]
                if target_directory == "~":
                    target_directory = os.environ.get("HOME", "")
                try:
                    os.chdir(target_directory)
                except Exception:
                    shell_error(f"cd: {parts[1]}: No such file or directory\n")
            close_handles()
            continue

        elif command_name == "complete":
            # Handles: complete -C <script> <cmd>, complete -r <cmd>, and complete -p <cmd>
            if len(parts) > 2 and parts[1] == "-C":
                script_path = parts[2]
                target_cmd = parts[3] if len(parts) > 3 else ""
                if target_cmd:
                    COMPLETIONS[target_cmd] = script_path
                    REMOVED_COMPLETIONS.discard(target_cmd)
            elif len(parts) > 2 and parts[1] == "-r":
                target_cmd = parts[2]
                COMPLETIONS.pop(target_cmd, None)
                REMOVED_COMPLETIONS.add(target_cmd)
            elif len(parts) > 2 and parts[1] == "-p":
                target_cmd = parts[2]
                if target_cmd in COMPLETIONS:
                    shell_print(f"complete -C {COMPLETIONS[target_cmd]} {target_cmd}")
                else:
                    shell_error(f"complete: {target_cmd}: no completion specification\n")
            close_handles()
            continue

        elif command_name == "jobs":
            clean_completed_jobs(background_jobs)
            for job in background_jobs:
                shell_print(f"[{job['job_number']}] {job['pid']} {job['status']} \t {job['command']}")
            background_jobs[:] = [j for j in background_jobs if j["status"] == "Running"]
            close_handles()
            continue

        elif command_name == "history":
            # --- Check for history -r <filename> ---
            if len(parts) > 2 and parts[1] == "-r":
                history_file = parts[2]
                try:
                    with open(history_file, "r") as f:
                        for line in f:
                            cleaned = line.strip()
                            if cleaned:
                                command_history.append(cleaned)
                except Exception as e:
                    shell_error(f"history: {e}\n")
                
                close_handles()
                continue

            # Standard history printing fallback
            for index, command__item in iter_history_entries(command_history, parts):
                shell_print(f"{index:5}  {command__item}")

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
