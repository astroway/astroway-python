"""Framework integrations.

Each submodule is opt-in via extras:

    pip install 'astroway[django]'   # → astroway.integrations.django
    pip install 'astroway[fastapi]'  # → astroway.integrations.fastapi

Importing without the extra installed raises ImportError with a helpful hint.
"""

from __future__ import annotations

__all__ = ["django", "fastapi"]
