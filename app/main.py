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

        command_name = command.split()[0]

        if command_name == "exit":
            return

        print(f"{command_name}: command not found")

if __name__ == "__main__":
    main()
