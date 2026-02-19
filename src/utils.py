def exists(file):
    try:
        with open(file):
            return True
    except OSError:
        return False
