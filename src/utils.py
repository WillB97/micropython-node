def _load_lookup_table():
    import json

    try:
        with open('/active/ids.json') as f:
            return json.load(f)
    except ValueError:
        return {}

NODE_LOOKUP = _load_lookup_table()

def exists(file):
    try:
        with open(file):
            return True
    except OSError:
        return False

def lookup_node_id(id):
    return NODE_LOOKUP.get(id, {"id": 0})["id"]
