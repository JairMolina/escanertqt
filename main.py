"""Compatibilidad: `python main.py` delega en el único punto de entrada, run_server.py."""
from run_server import main

if __name__ == "__main__":
    main()
