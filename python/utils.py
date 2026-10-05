def concat_(*args) -> str:
    """str() of each argument, joined with no separator.
    """
    return ''.join([str(x) for x in list(args)])
