# before any module starts a thread: freed memory goes back to the system instead of staying with one arena per thread (MEM-001)
from . import memguard as _memguard

_memguard.tune_malloc()
