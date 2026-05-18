import os
import sys


def main():
    BUILTINS = {"exit", "echo", "type"}

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

        if command_name == "exit":
            return

        if command_name == "echo":
            print(" ".join(parts[1:]))
            continue

        if command_name == "type":
            if len(parts) > 1:
                target_command = parts[1]
                
                # Step 1: Check if it's a builtin
                if target_command in BUILTINS:
                    print(f"{target_command} is a shell builtin")
                else:
                    # Step 2: Search for the executable in the PATH directories
                    path_env = os.environ.get("PATH", "")
                    # Split paths safely using the OS-specific path separator (e.g., ':')
                    directories = path_env.split(os.pathsep)
                    
                    found_path = None
                    for directory in directories:
                        # Construct the absolute path to the potential executable
                        full_path = os.path.join(directory, target_command)
                        
                        # Check if the file exists and has executable permissions
                        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                            found_path = full_path
                            break  # Stop searching after finding the first match
                    
                    if found_path:
                        print(f"{target_command} is {found_path}")
                    else:
                        print(f"{target_command}: not found")
            continue

        print(f"{command_name}: command not found")


if __name__ == "__main__":
    main()
