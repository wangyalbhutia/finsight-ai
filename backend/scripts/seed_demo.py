import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.seed import seed
if __name__ == "__main__":
    seed()
