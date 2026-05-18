import sys


def main():
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

        # Split the command into parts to separate the command name from its arguments
        parts = command.split()
        command_name = parts[0]

        if command_name == "exit":
            return
            
        if command_name == "echo":
            # Join all arguments after the command name with a space and print
            print(" ".join(parts[1:]))
            continue

        print(f"{command_name}: command not found")


if __name__ == "__main__":
    main()
