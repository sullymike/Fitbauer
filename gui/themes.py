"""Temas de color para la interfaz Qt."""
from __future__ import annotations


COLOR_THEMES: dict[str, dict] = {
    "blue": {
        "label": "Azul (clásico)",
        "window": "#eaf4fb", "base": "#ffffff", "alt_base": "#dcebf7",
        "text": "#0f3d5c", "button": "#d8ecf9", "button_text": "#0f3d5c",
        "highlight": "#38bdf8", "highlight_text": "#ffffff",
        "accent": "#075985", "accent_text": "#ffffff", "accent_sub": "#dff6ff",
        "title": "#075985", "disabled_text": "#9bb0bf", "disabled_base": "#eef3f7",
    },
    "soft": {
        "label": "Multicolor suave",
        "window": "#f4f2ec", "base": "#ffffff", "alt_base": "#ece7db",
        "text": "#33302a", "button": "#e7e1d3", "button_text": "#33302a",
        "highlight": "#6f9a8d", "highlight_text": "#ffffff",
        "accent": "#5b6c8f", "accent_text": "#ffffff", "accent_sub": "#eef0f6",
        "title": "#7a6a8f", "disabled_text": "#b3aa99", "disabled_base": "#efece4",
    },
    "teal": {
        "label": "Verde azulado",
        "window": "#eaf3f1", "base": "#ffffff", "alt_base": "#d7e8e4",
        "text": "#173a36", "button": "#d2e8e3", "button_text": "#173a36",
        "highlight": "#2fa39a", "highlight_text": "#ffffff",
        "accent": "#0f5e57", "accent_text": "#ffffff", "accent_sub": "#dff3ef",
        "title": "#0f5e57", "disabled_text": "#9bb5b0", "disabled_base": "#eef4f2",
    },
    "sepia": {
        "label": "Sepia cálido",
        "window": "#efe7d8", "base": "#fbf7ee", "alt_base": "#e6dcc8",
        "text": "#4a3f2e", "button": "#e3d7c0", "button_text": "#4a3f2e",
        "highlight": "#b08968", "highlight_text": "#ffffff",
        "accent": "#8a6d4e", "accent_text": "#ffffff", "accent_sub": "#f3ece0",
        "title": "#7c5e3f", "disabled_text": "#b3a48c", "disabled_base": "#efe9dd",
    },
    "dark": {
        "label": "Oscuro",
        "window": "#2b2f36", "base": "#1f2329", "alt_base": "#333941",
        "text": "#e6e9ee", "button": "#3a414b", "button_text": "#e6e9ee",
        "highlight": "#4f9fd6", "highlight_text": "#ffffff",
        "accent": "#11304a", "accent_text": "#ffffff", "accent_sub": "#cfe6f5",
        "title": "#8ec5e6", "disabled_text": "#6b727b", "disabled_base": "#262a30",
    },
    "system": {
        "label": "Sistema",
    },
}
