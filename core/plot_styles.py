"""Estilos de gráficos seleccionables desde la GUI.

Cada estilo es un dict con dos secciones:

* claves de color y elementos que el código de plot consume (``data``,
  ``model``, ``grid``, ``data_ms``, ``model_lw``, ``show_band``, ...).
* ``rc``: overrides de ``matplotlib.rcParams`` para tipografía y defaults
  globales.

La función :func:`get_style` devuelve el dict del estilo y :func:`apply_rc`
aplica los ``rc`` overrides sobre el ``rcParams`` global.
"""
from __future__ import annotations

from copy import deepcopy

import matplotlib

# ── Base "clásico" (replica el aspecto histórico de la GUI) ─────────────────
_CLASSIC = dict(
    # Colores principales
    fig_bg="#f8fbff", ax_bg="#fbfdff", res_bg="#fff7ed",
    title="#083344",
    grid="#c8e4f7", grid_alpha=0.85, grid_lw=0.8,
    tick="#243b53", spine="#8ecae6",
    lbl="#243b53",
    res_tick="#7c2d12", res_spine="#fdba74",
    res_zero="#9a3412", res_fill="#fb923c", res_line="#ea580c",
    res_grid="#fed7aa",
    data="#0f172a", baseline="#64748b", model="#dc2626",
    leg_face="#ffffff", leg_edge="#bae6fd", leg_text="#102a43",
    no_file="#075985",
    dist_line="#2563eb", dist_fill="#60a5fa",
    dist_grid="#bfdbfe", ann="#991b1b",
    # Tuning de elementos
    data_ms=4.0, data_alpha=0.88,
    model_lw=2.6, baseline_lw=1.35,
    res_line_lw=1.25, res_fill_alpha=0.22,
    component_lw=1.65, component_alpha=0.95,
    title_weight="bold",
    spines_hide=(),
    components_palette=("#16a34a", "#f97316", "#8b5cf6"),
    # Banda 1σ alrededor del modelo (compatible con la GUI; off por defecto)
    show_band=False, band_color="#dc2626", band_alpha=0.0,
    # rcParams overrides
    rc={},
)

# ── Moderno: flat, sans-serif moderno, marcador pequeño y banda 1σ ─────────
_MODERN = deepcopy(_CLASSIC)
_MODERN.update(
    fig_bg="#ffffff", ax_bg="#fafbfc", res_bg="#fafbfc",
    title="#1f2937",
    grid="#e5e7eb", grid_alpha=1.0, grid_lw=0.6,
    tick="#6b7280", spine="#d1d5db",
    lbl="#374151",
    res_tick="#6b7280", res_spine="#d1d5db",
    res_zero="#9ca3af", res_fill="#64748b", res_line="#64748b",
    res_grid="#e5e7eb",
    data="#2563eb", baseline="#94a3b8", model="#ef4444",
    leg_face="#ffffff", leg_edge="#e5e7eb", leg_text="#1f2937",
    no_file="#1f2937",
    dist_line="#2563eb", dist_fill="#93c5fd",
    dist_grid="#e5e7eb", ann="#dc2626",
    data_ms=3.5, data_alpha=0.55,
    model_lw=2.2, baseline_lw=1.0,
    res_line_lw=1.0, res_fill_alpha=0.10,
    component_lw=1.5, component_alpha=0.85,
    title_weight="semibold",
    spines_hide=("top", "right"),
    components_palette=("#10b981", "#f59e0b", "#8b5cf6"),
    show_band=True, band_color="#2563eb", band_alpha=0.12,
    rc={
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Inter", "Helvetica", "Arial", "sans-serif"],
        "font.size": 10.0,
        "axes.titlesize": 11.0,
        "axes.labelsize": 10.0,
        "xtick.labelsize": 9.0,
        "ytick.labelsize": 9.0,
        "legend.fontsize": 9.0,
        "legend.frameon": False,
    },
)

# ── Publicación: B/N, serif, marcador hollow, líneas finas ─────────────────
_PUBLICATION = deepcopy(_CLASSIC)
_PUBLICATION.update(
    fig_bg="#ffffff", ax_bg="#ffffff", res_bg="#ffffff",
    title="#000000",
    grid="#000000", grid_alpha=0.06, grid_lw=0.4,
    tick="#000000", spine="#000000",
    lbl="#000000",
    res_tick="#000000", res_spine="#000000",
    res_zero="#000000", res_fill="#000000", res_line="#000000",
    res_grid="#000000",
    data="#000000", baseline="#666666", model="#000000",
    leg_face="#ffffff", leg_edge="#000000", leg_text="#000000",
    no_file="#000000",
    dist_line="#000000", dist_fill="#bbbbbb",
    dist_grid="#000000", ann="#000000",
    data_ms=3.5, data_alpha=1.0,
    model_lw=1.2, baseline_lw=0.7,
    res_line_lw=0.9, res_fill_alpha=0.10,
    component_lw=0.9, component_alpha=1.0,
    title_weight="normal",
    spines_hide=(),
    components_palette=("#404040", "#808080", "#a0a0a0"),
    show_band=False, band_color="#000000", band_alpha=0.0,
    rc={
        "font.family": "serif",
        "font.serif": ["DejaVu Serif", "Times New Roman", "Times", "serif"],
        "font.size": 10.5,
        "axes.titlesize": 11.5,
        "axes.labelsize": 11.0,
        "xtick.labelsize": 10.0,
        "ytick.labelsize": 10.0,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "axes.linewidth": 0.8,
        "legend.frameon": True,
        "legend.edgecolor": "#000000",
    },
)

# ── Oscuro: paleta oscura coherente, modo escritorio nocturno ─────────────
_DARK = deepcopy(_CLASSIC)
_DARK.update(
    fig_bg="#1c1c1e", ax_bg="#2a2a2a", res_bg="#252520",
    title="#e2e8f0",
    grid="#444444", grid_alpha=0.45, grid_lw=0.7,
    tick="#a6adc8", spine="#6c7086",
    lbl="#a6adc8",
    res_tick="#a6adc8", res_spine="#6c7086",
    res_zero="#6c7086", res_fill="#fb923c", res_line="#fdba74",
    res_grid="#3a3a3a",
    data="#e2e8f0", baseline="#94a3b8", model="#f87171",
    leg_face="#2a2a2a", leg_edge="#6c7086", leg_text="#e2e8f0",
    no_file="#a6adc8",
    dist_line="#89b4fa", dist_fill="#89b4fa",
    dist_grid="#3a3a3a", ann="#f87171",
    data_ms=3.5, data_alpha=0.75,
    model_lw=2.2, baseline_lw=1.1,
    res_line_lw=1.1, res_fill_alpha=0.18,
    component_lw=1.5, component_alpha=0.9,
    title_weight="bold",
    spines_hide=("top", "right"),
    components_palette=("#34d399", "#fbbf24", "#a78bfa"),
    show_band=True, band_color="#e2e8f0", band_alpha=0.08,
    rc={
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Inter", "Helvetica", "Arial", "sans-serif"],
        "font.size": 10.0,
        "legend.frameon": False,
    },
)

STYLES: dict[str, dict] = {
    "classic": _CLASSIC,
    "modern": _MODERN,
    "publication": _PUBLICATION,
    "dark": _DARK,
}

STYLE_ORDER = ("classic", "modern", "publication", "dark")


def get_style(name: str) -> dict:
    """Devuelve el dict del estilo (clonado, para no mutar el global)."""
    return deepcopy(STYLES.get(name, STYLES["classic"]))


def apply_rc(name: str) -> None:
    """Aplica los rcParams del estilo sobre la configuración global."""
    style = STYLES.get(name)
    if style is None:
        return
    rc = style.get("rc") or {}
    for k, v in rc.items():
        matplotlib.rcParams[k] = v
