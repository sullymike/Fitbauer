"""Configuración compartida de pytest.

Monkeypatch para entornos de desarrollo con NumPy<2: añade ``np.trapezoid``
(introducido en NumPy 2.0) apuntando a ``np.trapz`` si no existe.

En CI ``requirements.txt`` fija ``numpy>=2.0`` y este monkeypatch es no-op.
"""
from __future__ import annotations

import numpy as np

if not hasattr(np, "trapezoid"):
    np.trapezoid = np.trapz  # type: ignore[attr-defined]
