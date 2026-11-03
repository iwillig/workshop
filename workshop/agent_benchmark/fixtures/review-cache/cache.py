def add_entry(key, value, cache={}):
    """Add one value to a new cache unless a cache was provided."""
    cache[key] = value
    return cache
