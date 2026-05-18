import sys


def main():
    # Keep track of the shell builtins we've supported so far
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
            # Ensure the user actually provided an argument to inspect
            if len(parts) > 1:
                target_command = parts[1]
                if target_command in BUILTINS:
                    print(f"{target_command} is a shell builtin")
                else:
                    print(f"{target_command}: not found")
            continue

        print(f"{command_name}: command not found")


if __name__ == "__main__":
    main()
