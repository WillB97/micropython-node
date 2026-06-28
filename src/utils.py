def exists(file):
    try:
        with open(file):
            return True
    except OSError:
        return False

def lookup_node_id():
    import machine
    import json
    client_id = machine.unique_id().hex()

    try:
        with open('/active/ids.json') as f:
            id_map =json.load(f)
    except ValueError:
        id_map = {}

    return id_map.get(client_id, {"id": 0})["id"]
