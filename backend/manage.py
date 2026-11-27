#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    # For the archive commands' pyarrow: Arrow's own allocator keeps much of what counting a
    # month's game history frees, about 0.25 GB more at the peak than the system's. Arrow
    # reads this once, so it's set before anything imports pyarrow.
    os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
