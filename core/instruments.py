"""Equipos (espectrómetros) como perfiles: cómo se leen y preparan sus datos.

Un perfil guarda las correcciones a la lectura automática
(:class:`core.spectrum_import.ImportHints`; solo lo que el usuario fijó, no lo
detectado en un fichero concreto) y cómo se preparan sus espectros: forma de
onda, plegado y sentido del eje. No hay equipos predefinidos ni límite de
número: cada laboratorio da de alta los suyos.

Cada equipo vive en su carpeta, ``<raíz>/<equipo>/``, con su perfil
(``instrument.json``) y sus calibraciones (``calibrations.json`` y la copia de
cada espectro de calibración en ``calibrations/``). La raíz se puede compartir
(p. ej. una carpeta de red del grupo).

**Elección de la calibración** (``calibration_rule`` del equipo):

- ``"date"``: a un espectro medido el día *D* le corresponde la última
  calibración del equipo con fecha ≤ *D* (la vigente cuando se midió).
- ``"latest"``: la calibración más reciente del equipo, sin mirar fechas
  (equipos cuyos ficheros no traen fecha de medida).

Además, la GUI permite elegir una calibración concreta a mano
(:meth:`InstrumentLibrary.choose_calibration` con ``record_id``).

**Reconocimiento**: un equipo puede declarar cómo reconocer sus ficheros
(``match_text``: textos de su cabecera o pie; ``match_name``: patrones del
nombre de fichero, ``*.ws5``, ``FeB*``). Dentro de cada lista basta uno; si
declara las dos, se exigen ambas. Al abrir un fichero sin elegir equipo, el que
lo reconozca **en exclusiva** se aplica solo (:meth:`InstrumentLibrary.recognize`).
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import re
import shutil
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from core.data_io import CONFIG_DIR
from core.folding import canonical_fold_mode
from core.constants import canonical_sextet_pattern
from core.spectrum_import import (
    DATE_ORDERS, ImportedSpectrum, ImportHints, read_spectrum_file, read_text,
)

#: Reglas para elegir la calibración de un espectro (ver el docstring).
CALIBRATION_RULES = ("date", "latest")

#: Raíz por defecto de la biblioteca de equipos.
DEFAULT_INSTRUMENTS_DIR = CONFIG_DIR / "instruments"
PROFILE_FILE = "instrument.json"
CALIBRATIONS_FILE = "calibrations.json"
CALIBRATIONS_DIR = "calibrations"


@dataclass
class InstrumentProfile:
    name: str
    import_hints: ImportHints = field(default_factory=ImportHints)
    drive_form: str = "triangular"
    fold_mode: str = "fold"
    reverse_velocity: bool = False
    # Cómo leer fechas numéricas ambiguas (03/04/2025) en sus ficheros.
    date_order: str = "dmy"
    notes: str = ""
    # Cómo se elige la calibración de cada espectro (CALIBRATION_RULES).
    calibration_rule: str = "date"
    # Reconocimiento automático de sus ficheros (vacías = no se reconoce).
    match_text: list[str] = field(default_factory=list)
    match_name: list[str] = field(default_factory=list)

    @property
    def recognizable(self) -> bool:
        return bool(self.match_text or self.match_name)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "import_hints": self.import_hints.to_dict(),
            "drive_form": self.drive_form,
            "fold_mode": self.fold_mode,
            "reverse_velocity": bool(self.reverse_velocity),
            "date_order": self.date_order,
            "notes": self.notes,
            "calibration_rule": self.calibration_rule,
            "match_text": list(self.match_text),
            "match_name": list(self.match_name),
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
            date_order=(data.get("date_order") if data.get("date_order") in DATE_ORDERS
                        else "dmy"),
            notes=str(data.get("notes", "")),
            calibration_rule=(data.get("calibration_rule")
                              if data.get("calibration_rule") in CALIBRATION_RULES else "date"),
            match_text=_str_list(data.get("match_text")),
            match_name=_str_list(data.get("match_name")),
        )


def _str_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def split_patterns(text: str) -> list[str]:
    """``"FeB-1; *.ws5"`` → ``["FeB-1", "*.ws5"]`` (separador ``;``)."""
    return [t.strip() for t in str(text).split(";") if t.strip()]


def recognition_text(path: str | Path,
                     spectrum: ImportedSpectrum | None = None) -> list[str]:
    """Líneas de cabecera y pie de un fichero, donde se busca ``match_text``.

    Si el lector no encuentra datos, las primeras líneas del texto.
    """
    if spectrum is None:
        try:
            spectrum = read_spectrum_file(path)
        except (OSError, ValueError):
            try:
                return read_text(path).splitlines()[:100]
            except OSError:
                return []
    return list(spectrum.header) + list(spectrum.footer)


def profile_matches(profile: InstrumentProfile, file_name: str,
                    lines: list[str]) -> bool:
    """¿Reconoce ``profile`` el fichero? Sin criterios, nunca."""
    if not profile.recognizable:
        return False
    if profile.match_name:
        name = file_name.casefold()
        if not any(fnmatch.fnmatchcase(name, pat.casefold()) for pat in profile.match_name):
            return False
    if profile.match_text:
        text = "\n".join(lines).casefold()
        if not any(pat.casefold() in text for pat in profile.match_text):
            return False
    return True


@dataclass
class CalibrationRecord:
    """Una calibración de velocidad del equipo, vigente desde ``date``.

    ``vmax`` es la Vmax ajustada con el patrón ``sextet_pattern`` (la GUI la
    convierte al patrón activo). ``file_name`` es la copia del espectro de
    calibración dentro de la carpeta del equipo, si se guardó.
    """
    date: dt.date
    vmax: float
    sextet_pattern: str = "normos"
    isomer_shift: float | None = None
    sample: str = ""
    file_name: str | None = None
    notes: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return {"id": self.id, "date": self.date.isoformat(), "vmax": float(self.vmax),
                "sextet_pattern": self.sextet_pattern, "isomer_shift": self.isomer_shift,
                "sample": self.sample, "file_name": self.file_name, "notes": self.notes}

    @classmethod
    def from_dict(cls, data: dict) -> "CalibrationRecord":
        iso = data.get("isomer_shift")
        return cls(
            date=dt.date.fromisoformat(str(data["date"])[:10]),
            vmax=float(data["vmax"]),
            sextet_pattern=canonical_sextet_pattern(data.get("sextet_pattern") or "normos"),
            isomer_shift=None if iso in (None, "") else float(iso),
            sample=str(data.get("sample", "")),
            file_name=data.get("file_name") or None,
            notes=str(data.get("notes", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
        )


def calibration_for_date(records: list[CalibrationRecord],
                         date: dt.date) -> CalibrationRecord | None:
    """La calibración vigente el día ``date``: la última con fecha ≤ ``date``.

    A igual fecha gana la añadida después. ``None`` si todas son posteriores.
    """
    valid = [(r.date, i, r) for i, r in enumerate(records) if r.date <= date]
    return max(valid, key=lambda t: (t[0], t[1]))[2] if valid else None


def latest_calibration(records: list[CalibrationRecord]) -> CalibrationRecord | None:
    """La calibración más reciente (a igual fecha, la añadida después)."""
    if not records:
        return None
    return max(enumerate(records), key=lambda t: (t[1].date, t[0]))[1]


@dataclass
class CalibrationChoice:
    """Calibración elegida para un espectro y por qué.

    ``rule``: ``"date"``, ``"latest"`` o ``"manual"``. ``date``/``origin`` son
    la fecha de medida y de dónde salió (``"header"``/``"file"``); pueden
    faltar sin que eso impida elegir con ``"latest"`` o ``"manual"``.
    """
    record: CalibrationRecord | None
    date: dt.date | None = None
    origin: str | None = None
    rule: str = "date"


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

    def recognize(self, path: str | Path,
                  spectrum: ImportedSpectrum | None = None) -> list[InstrumentProfile]:
        """Equipos que reconocen el fichero (vacía si ninguno declara criterios).

        Solo debe aplicarse automáticamente si hay **uno**: con varios, el
        usuario elige (los criterios se solapan).
        """
        profiles = [p for p in self.list() if p.recognizable]
        if not profiles:
            return []
        lines = recognition_text(path, spectrum)
        name = Path(path).name
        return [p for p in profiles if profile_matches(p, name, lines)]

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

    # ── Calibraciones ─────────────────────────────────────────────────────
    def calibrations_folder(self, name: str) -> Path:
        return self._folder(name) / CALIBRATIONS_DIR

    def calibrations(self, name: str) -> list[CalibrationRecord]:
        """Calibraciones del equipo, de la más antigua a la más reciente."""
        path = self._folder(name) / CALIBRATIONS_FILE
        if not path.is_file():
            return []
        out = []
        for item in json.loads(path.read_text(encoding="utf-8")):
            try:
                out.append(CalibrationRecord.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out, key=lambda r: r.date)

    def _write_calibrations(self, name: str, records: list[CalibrationRecord]) -> None:
        path = self._folder(name) / CALIBRATIONS_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps([r.to_dict() for r in records], ensure_ascii=False,
                                  indent=2), encoding="utf-8")
        tmp.replace(path)

    def add_calibration(self, name: str, record: CalibrationRecord,
                        source_file: str | Path | None = None) -> CalibrationRecord:
        """Añade una calibración; si se da ``source_file``, guarda una copia."""
        if self.get(name) is None:
            raise KeyError(name)
        if source_file is not None:
            src = Path(source_file)
            folder = self.calibrations_folder(name)
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / f"{record.date.isoformat()}_{record.id}_{src.name}"
            shutil.copy2(src, dest)
            record.file_name = dest.name
        records = self.calibrations(name)
        records.append(record)
        self._write_calibrations(name, records)
        return record

    def remove_calibration(self, name: str, record_id: str) -> bool:
        records = self.calibrations(name)
        keep = [r for r in records if r.id != record_id]
        if len(keep) == len(records):
            return False
        gone = next(r for r in records if r.id == record_id)
        if gone.file_name:
            (self.calibrations_folder(name) / gone.file_name).unlink(missing_ok=True)
        self._write_calibrations(name, keep)
        return True

    def calibration_file(self, name: str, record: CalibrationRecord) -> Path | None:
        if not record.file_name:
            return None
        path = self.calibrations_folder(name) / record.file_name
        return path if path.is_file() else None

    def calibration_for(self, name: str, date: dt.date) -> CalibrationRecord | None:
        return calibration_for_date(self.calibrations(name), date)

    def choose_calibration(self, name: str, spectrum: ImportedSpectrum | None = None,
                           path: str | Path | None = None, *,
                           record_id: str | None = None) -> CalibrationChoice:
        """Calibración que corresponde a un espectro de ``name``.

        Con ``record_id``, esa calibración (elegida a mano). Si no, la regla
        del equipo: ``"latest"`` o ``"date"`` (fecha de medida del fichero:
        cabecera/pie o, si no hay, fecha del fichero).
        """
        from core.spectrum_import import measurement_date
        profile = self.get(name)
        if profile is None:
            return CalibrationChoice(None)
        date = origin = None
        if spectrum is not None:
            date, origin = measurement_date(spectrum, path, profile.date_order)
        records = self.calibrations(name)
        if record_id:
            record = next((r for r in records if r.id == record_id), None)
            return CalibrationChoice(record, date, origin, "manual")
        if profile.calibration_rule == "latest":
            return CalibrationChoice(latest_calibration(records), date, origin, "latest")
        record = calibration_for_date(records, date) if date is not None else None
        return CalibrationChoice(record, date, origin, "date")

    def delete(self, name: str) -> bool:
        """Borra el perfil; sus calibraciones y la carpeta se conservan si las hay."""
        folder = self._folder(name)
        path = folder / PROFILE_FILE
        if self.get(name) is None:
            return False
        path.unlink()
        if folder.is_dir() and not any(folder.iterdir()):
            shutil.rmtree(folder, ignore_errors=True)
        return True
