import machine, sys

# Add /active to path so the OTA main can be imported correctly
sys.path.insert(1, '/active')

try:
    import active.main
except Exception as e:
    print("Fatal error in main:")
    sys.print_exception(e)
except KeyboardInterrupt:
    pass
else:
    # Following a normal Exception or main() exiting, reset the board.
    # Following a non-Exception error such as KeyboardInterrupt (Ctrl-C),
    # this code will drop to a REPL. Place machine.reset() in a finally
    # block to always reset, instead.
    machine.reset()