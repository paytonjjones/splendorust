"""Use the residual history loader; other checkpoint kinds keep their original loader."""
import service
from capacity_history import load

service.load = load

if __name__ == "__main__":
    service.main()
