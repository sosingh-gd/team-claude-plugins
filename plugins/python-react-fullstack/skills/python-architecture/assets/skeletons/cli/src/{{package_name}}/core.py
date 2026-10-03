"""Business logic, independent of the CLI so it can be tested and reused directly."""


def build_greeting(name: str, *, shout: bool = False) -> str:
    greeting = f"Hello, {name}!"
    return greeting.upper() if shout else greeting
