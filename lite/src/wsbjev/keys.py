r"""Read API keys from the process env, falling back to the Windows user env (HKCU\Environment).

Keys never live in files in this project.
"""
import os


def get(name: str) -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            v, _ = winreg.QueryValueEx(k, name)
            return v or ""
    except (OSError, ImportError):  # ImportError: not Windows (no winreg)
        return ""
