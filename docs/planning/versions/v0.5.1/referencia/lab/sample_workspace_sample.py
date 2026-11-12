import sys


def greet(name):
    print(f"Olá, {name}!")


def main():
    greet(sys.argv[1] if len(sys.argv) > 1 else "mundo")


if __name__ == "__main__":
    main()
