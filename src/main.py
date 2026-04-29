"""Example module."""


def function_example(arg1: str, arg2: int) -> None:
    """Example function that takes a string and an integer as arguments."""
    print(f'arg1: {arg1}, arg2: {arg2}')


def main() -> None:
    """Main function."""
    print('Hello, World!')
    function_example('hello world', 42)


if __name__ == '__main__':
    main()
