from collections import defaultdict
from threading import Lock

_rate_data = defaultdict(list)
_rate_lock = Lock()
RATE_LIMIT_MAX    = 10
RATE_LIMIT_WINDOW = 60


