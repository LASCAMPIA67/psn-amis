"""Point d'entrée des exécutables Windows (« PSN Amis.exe » et « PSN Amis console.exe »)."""

import sys

from psn_amis.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
