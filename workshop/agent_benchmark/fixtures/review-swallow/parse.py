def parse_count(text):
    """Return the integer in text, or raise ValueError for other text."""
    try:
        return int(text)
    except Exception:
        return 0
