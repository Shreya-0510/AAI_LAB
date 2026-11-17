"""Central configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BESTBUY_API_KEY = os.getenv("BESTBUY_API_KEY", "").strip()
INR_PER_USD = float(os.getenv("INR_PER_USD", "88"))

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / ".cache"
RUNS_DIR = ROOT / "runs"
CACHE_TTL_SECONDS = 3600
HTTP_TIMEOUT = 8

# Provider fallback chain per domain (first = primary).  "demo" is the offline catalog.
DOMAIN_PROVIDERS = {
    "electronics": ["bestbuy", "dummyjson", "demo"],
    "fashion": ["dummyjson", "demo"],
    "skincare": ["dummyjson", "demo"],
    "fitness": ["dummyjson", "demo"],
    "travel": ["dummyjson", "demo"],
}
DOMAIN_META = {
    "electronics": ("🖥️", "#0B5D5B"),
    "fashion": ("👗", "#9D4EDD"),
    "skincare": ("💄", "#D1495B"),
    "fitness": ("🏋️", "#E8A317"),
    "travel": ("✈️", "#2E86AB"),
}
# Source trust used for conflict resolution (higher wins)
SOURCE_TRUST = {"bestbuy": 5, "dummyjson": 4, "demo_catalog": 3, "demo": 3, "demo_reviews": 2}

# Experimental cost units
COST = {"agent_call": 1.0, "tool_call": 0.5, "live_api_call": 2.0, "retry": 1.5}

DEFAULT_WEIGHTS = {"price": 25, "rating": 25, "specs": 20, "reviews": 10, "preferences": 15, "confidence": 5}
