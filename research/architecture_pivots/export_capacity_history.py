"""Use the residual history loader; other checkpoint kinds keep their original loader."""
import export
from capacity_history import load

export.load = load

if __name__ == "__main__":
    export.main()
