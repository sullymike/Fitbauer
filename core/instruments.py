"""Equipos (espectrómetros) como perfiles: cómo se leen y preparan sus datos.

Un perfil guarda las correcciones a la lectura automática
(:class:`core.spectrum_import.ImportHints`; solo lo que el usuario fijó, no lo
detectado en un fichero concreto) y cómo se preparan sus espectros: forma de
onda, plegado y sentido del eje. No hay equipos predefinidos ni límite de
número: cada laboratorio da de alta los suyos.

Cada equipo vive en su carpeta, ``<raíz>/<equipo>/instrument.json``, para que
la misma carpeta pueda guardar después sus calibraciones y para que la raíz se
pueda compartir (p. ej. una carpeta de red del grupo).
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from core.data_io import CONFIG_DIR
from core.folding import canonical_fold_mode
from core.spectrum_import import ImportHints

#: Raíz por defecto de la biblioteca de equipos.
DEFAULT_INSTRUMENTS_DIR = CONFIG_DIR / "instruments"
PROFILE_FILE = "instrument.json"


@dataclass
class InstrumentProfile:
    name: str
    import_hints: ImportHints = field(default_factory=ImportHints)
    drive_form: str = "triangular"
    fold_mode: str = "fold"
    reverse_velocity: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "import_hints": self.import_hints.to_dict(),
            "drive_form": self.drive_form,
            "fold_mode": self.fold_mode,
            "reverse_velocity": bool(self.reverse_velocity),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InstrumentProfile":
        drive = str(data.get("drive_form", "triangular"))
        return cls(
            name=str(data["name"]),
            import_hints=ImportHints.from_dict(data.get("import_hints")),
            drive_form=drive if drive in ("triangular", "sine") else "triangular",
            fold_mode=canonical_fold_mode(data.get("fold_mode")),
            reverse_velocity=bool(data.get("reverse_velocity", False)),
            notes=str(data.get("notes", "")),
        )


def instrument_slug(name: str) -> str:
    """Nombre de carpeta seguro y estable para un equipo."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return slug or "equipo"


class InstrumentLibrary:
    """Equipos guardados bajo una carpeta raíz (uno por subcarpeta)."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else DEFAULT_INSTRUMENTS_DIR

    def _folder(self, name: str) -> Path:
        return self.root / instrument_slug(name)

    def list(self) -> list[InstrumentProfile]:
        out = []
        if self.root.is_dir():
            for path in sorted(self.root.glob(f"*/{PROFILE_FILE}")):
                try:
                    out.append(InstrumentProfile.from_dict(
                        json.loads(path.read_text(encoding="utf-8"))))
                except (OSError, ValueError, KeyError, TypeError):
                    continue        # un perfil roto no tumba la lista
        return sorted(out, key=lambda p: p.name.casefold())

    def names(self) -> list[str]:
        return [p.name for p in self.list()]

    def get(self, name: str) -> InstrumentProfile | None:
        path = self._folder(name) / PROFILE_FILE
        if not path.is_file():
            return None
        profile = InstrumentProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return profile if profile.name == name else None

    def save(self, profile: InstrumentProfile) -> Path:
        """Guarda (o sustituye) el equipo; escritura atómica."""
        if not profile.name.strip():
            raise ValueError("instrument name is empty")
        folder = self._folder(profile.name)
        path = folder / PROFILE_FILE
        if path.is_file():
            old = json.loads(path.read_text(encoding="utf-8")).get("name")
            if old != profile.name:
                # Dos nombres que dan la misma carpeta («Equipo 1» / «equipo-1»).
                raise ValueError(f"'{profile.name}' clashes with existing '{old}'")
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(path)
        return path

    def delete(self, name: str) -> bool:
        """Borra el perfil. La carpeta solo si queda vacía (calibraciones)."""
        folder = self._folder(name)
        path = folder / PROFILE_FILE
        if self.get(name) is None:
            return False
        path.unlink()
        if folder.is_dir() and not any(folder.iterdir()):
            shutil.rmtree(folder, ignore_errors=True)
        return True
