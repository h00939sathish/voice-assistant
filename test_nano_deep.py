
import nanowakeword
import os

print(f"Data: {nanowakeword.data}")
# Use os.listdir if it's a module path or check attributes
if hasattr(nanowakeword.data, '__file__'):
    print(f"Data file: {nanowakeword.data.__file__}")
    print(f"Data dir: {os.path.dirname(nanowakeword.data.__file__)}")
    try:
        print(f"Contents: {os.listdir(os.path.dirname(nanowakeword.data.__file__))}")
    except:
        pass

from nanowakeword import NanoInterpreter
print(f"NanoInterpreter: {NanoInterpreter}")
# help(NanoInterpreter) # Might be too verbose
print(f"NanoInterpreter init args: {NanoInterpreter.__init__.__code__.co_varnames}")

try:
    # Try to list models from utils if possible
    from nanowakeword import utils
    print(f"Utils dir: {dir(utils)}")
except:
    pass
