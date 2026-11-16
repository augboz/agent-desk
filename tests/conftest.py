import os
import sys

# The app is a folder of plain modules, not a package: make them importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
