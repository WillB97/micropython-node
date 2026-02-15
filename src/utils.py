def exists(file):
    try:
        with open(file):
            return True
    except OSError:
        return False

# TODO probably remove
def do_library_install(file):
    import mip
    if not exists(file):
        print(f"No library file: {file}")
        return
    with open(file) as f:
        for line in f:
            pkg, *other = line.split()
            if other:
                pkg_ver = other[0]
                print(f"Installing: {pkg}@{pkg_ver}")
                mip.install(pkg, version=pkg_ver)
            else:
                print(f"Installing: {pkg}")
                mip.install(pkg)
