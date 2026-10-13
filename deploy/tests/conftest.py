import sys
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY))
