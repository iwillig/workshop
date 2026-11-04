def page_count(items, size):
    """Return the number of pages needed to show all items."""
    return len(items) // size
