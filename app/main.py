import sys


def main():
    sys.stdout.write("$ ")
    sys.stdout.flush()

    user_input = sys.stdin.readline()
    if not user_input:
        return

    command = user_input.strip()
    if command:
        command_name = command.split()[0]
        print(f"{command_name}: command not found")


if __name__ == "__main__":
    main()
