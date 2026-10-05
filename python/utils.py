from typing import Any


def concat_(*args: Any) -> str:
    """str() of each argument, joined with no separator.
    """
    return ''.join([str(x) for x in list(args)])
