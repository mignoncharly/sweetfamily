"""Fail closed for known debuggers/dump configuration before serving private data."""

import os
import sys
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def harden_process():
    if settings.APP_ENV == "local":
        return
    if sys.gettrace() is not None or sys.getprofile() is not None:
        raise ImproperlyConfigured("Debugger/profiler forbidden for private production process")
    if any(name in sys.modules for name in ("debugpy", "pydevd", "pdb")):
        raise ImproperlyConfigured("Debugger module forbidden")
    if os.environ.get("PYTHONFAULTHANDLER") or os.environ.get("PYTHONINSPECT"):
        raise ImproperlyConfigured("Crash/debug hooks forbidden")
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if sys.platform == "linux":
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            # Linux UAPI constants: PR_SET_DUMPABLE=4, PR_GET_DUMPABLE=3.
            args = (ctypes.c_ulong(0),) * 4
            if libc.prctl(ctypes.c_int(4), *args) != 0 or libc.prctl(ctypes.c_int(3), *args) != 0:
                raise ImproperlyConfigured("Cannot disable process dumps")
    elif os.name == "nt":
        import winreg

        # WER LocalDumps works independently of normal WER reporting. Never edit system policy.
        for path in (
            r"SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps",
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AeDebug",
        ):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                ) as key:
                    if path.endswith("LocalDumps"):
                        raise ImproperlyConfigured(
                            "OS dump collection must be disabled by operator"
                        )
                    try:
                        debugger, _ = winreg.QueryValueEx(key, "Debugger")
                    except FileNotFoundError:
                        debugger = ""
                    if debugger:
                        raise ImproperlyConfigured(
                            "OS postmortem debugger must be disabled by operator"
                        )
            except FileNotFoundError:
                pass
    else:
        raise ImproperlyConfigured("Unqualified process dump policy")
    os.environ["PYTHONBREAKPOINT"] = "0"
