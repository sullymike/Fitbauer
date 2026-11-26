"""De un fichero a un espectro listo para ajustar (sin GUI).

Fuente única de la carga para la ventana, el ajuste en serie, la comparación
y la sesión sin GUI (:class:`core.session.HeadlessSession`):

- :func:`open_spectrum` lee el fichero (:mod:`core.spectrum_import`) y, si se
  abre con un equipo, elige su calibración (:meth:`InstrumentLibrary.choose_calibration`).
- :func:`calibration_after_load` es la **prioridad entre calibraciones** al
  cargar, escrita en un solo sitio.
- :func:`prepare_spectrum` dobla (o no) las cuentas y construye el eje de
  velocidad según la adquisición (:class:`Acquisition`).

Prioridad de calibraciones al cargar un espectro
------------------------------------------------
1. **Eje de velocidad propio** (CSV/TXT procesado): el fichero trae su
   calibración; sustituye a la fijada (``source="embedded"``, Vmax = max|v|) y
   conserva el δ(α-Fe) que hubiera. Es **solo de ese fichero**: guarda la que
   sustituyó (``replaced_calibration``) y la Vmax del panel (``replaced_vmax``).
2. **Cuentas abiertas con un equipo** que tiene calibración aplicable (por
   fecha, la más reciente o elegida a mano): esa (``source="instrument"``).
3. **En otro caso**, la calibración fijada que hubiera (local, de la web o de
   un equipo) se mantiene y su Vmax se impone. Si lo último abierto fue un
   fichero con eje propio, vuelve la que ese fichero sustituyó: el máximo |v|
   de un fichero procesado no es la Vmax de unas cuentas en bruto.

La Vmax se lleva al patrón del sextete activo con :func:`calibration_vmax`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.constants import canonical_sextet_pattern, convert_vmax
from core.folding import (
    EDGE_TRIM_DEFAULT,
    canonical_fold_mode,
    channel_velocity_axis,
    detect_fold_center,
    fold_center_window,
    prepare_channel_counts,
    read_normos_folding_point,
)
from core.spectrum_import import ImportedSpectrum, ImportHints, read_spectrum_file


@dataclass(frozen=True)
class Acquisition:
    """Cómo se adquirió un espectro por canales: forma de onda, plegado y sentido."""
    drive_form: str = "triangular"
    fold_mode: str = "fold"
    reverse: bool = False

    @classmethod
    def of_profile(cls, profile) -> "Acquisition":
        """La de un :class:`~core.instruments.InstrumentProfile`."""
        return cls(profile.drive_form, profile.fold_mode, bool(profile.reverse_velocity))


@dataclass
class PreparedSpectrum:
    """Cuentas listas para ajustar: doblado, normalizado y eje de velocidad.

    ``velocity`` es ``None`` si se preparó sin Vmax (la sesión sin GUI lo
    construye al ajustar, con la Vmax del modelo).
    """
    counts: np.ndarray
    center: float
    folded: np.ndarray
    sigma: np.ndarray
    y: np.ndarray
    norm: float
    velocity: np.ndarray | None


def file_fold_center(path: str | Path, acquisition: Acquisition,
                     n_channels: int) -> float | None:
    """Punto de plegado de un ajuste previo de NORMOS (``.RES`` junto al
    fichero, «Final folding point»), si procede doblar.

    ``None`` si no lo hay, no se dobla o no es plausible: fuera de la ventana
    del centro (N/2 ± margen). Hay ``.RES`` con 0 y, en 1024 canales, la
    regla de :func:`read_normos_folding_point` (≥ 400 → ÷2) lo parte por la
    mitad; en esos casos se detecta.
    """
    if (acquisition.drive_form == "sine"
            or canonical_fold_mode(acquisition.fold_mode) == "single_sweep"):
        return None
    try:
        center = read_normos_folding_point(Path(path))
    except (OSError, ValueError):
        return None
    if center is None:
        return None
    lo, hi = fold_center_window(int(n_channels), drive_form=acquisition.drive_form)
    return float(center) if lo <= center <= hi else None


def initial_fold_center(counts: np.ndarray, acquisition: Acquisition,
                        path: str | Path | None = None) -> float:
    """Centro con que se dobla un espectro al abrirlo: el de un ajuste previo
    de NORMOS si es plausible (:func:`file_fold_center`) o el detectado."""
    counts = np.asarray(counts, dtype=float)
    if path is not None:
        center = file_fold_center(path, acquisition, counts.size)
        if center is not None:
            return center
    return float(detect_fold_center(counts, drive_form=acquisition.drive_form,
                                    fold_mode=acquisition.fold_mode))


def prepare_spectrum(counts: np.ndarray, acquisition: Acquisition,
                     vmax: float | None, *, center: float | None = None,
                     path: str | Path | None = None,
                     edge_trim: int = EDGE_TRIM_DEFAULT) -> PreparedSpectrum:
    """Dobla (o no) ``counts`` y construye su eje de velocidad.

    Sin ``center``, :func:`initial_fold_center` (el de NORMOS junto a
    ``path`` si es plausible, o el detectado). Al doblar, el
    recorte de bordes del eje se deduce del nº de puntos, igual que el de los
    datos (también con el recorte adaptativo).
    """
    counts = np.asarray(counts, dtype=float)
    if center is None:
        center = initial_fold_center(counts, acquisition, path)
    center = float(center)
    folded, sigma, y, norm = prepare_channel_counts(
        counts, center, fold_mode=acquisition.fold_mode,
        drive_form=acquisition.drive_form, edge_trim=int(edge_trim))
    velocity = None
    if vmax is not None:
        velocity = channel_velocity_axis(
            counts.size, float(vmax), y.size, center=center,
            fold_mode=acquisition.fold_mode, drive_form=acquisition.drive_form,
            reverse=acquisition.reverse)
    return PreparedSpectrum(counts=counts, center=center, folded=folded, sigma=sigma,
                            y=y, norm=float(norm), velocity=velocity)


# ── Calibraciones ─────────────────────────────────────────────────────────
def calibration_pattern(info: dict | None) -> str | None:
    """Patrón del sextete con que se obtuvo una calibración.

    ``None`` si no depende de él (eje de velocidad propio del fichero). Sin
    la marca, las calibraciones locales anteriores a la v5.2.5 se hicieron
    con el patrón histórico; las de la API web son VMAX de NORMOS (la API dice
    «legacy» en las que la web guardó con su ajuste antiguo).
    """
    if not info or info.get("source") == "embedded":
        return None
    defecto = "normos" if info.get("source") == "web_api" else "legacy"
    try:
        return canonical_sextet_pattern(info.get("sextet_pattern") or defecto)
    except ValueError:
        return defecto


def calibration_vmax(info: dict | None, active_pattern: str | None) -> float | None:
    """Vmax de una calibración llevada al patrón activo (o ``None`` si no hay)."""
    if not info:
        return None
    value = info.get("velocity_calibrated")
    try:
        vmax = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if vmax is None:
        return None
    origen = calibration_pattern(info)
    return vmax if origen is None else convert_vmax(vmax, origen, active_pattern)


def embedded_calibration_info(path: str | Path, file_vmax: float,
                              previous: dict | None = None,
                              vmax_before: float | None = None) -> dict:
    """Calibración que trae un fichero con eje de velocidad propio.

    Conserva el δ(α-Fe) de la calibración anterior (sigue haciendo falta para
    referir δ al α-Fe) y guarda la que sustituye y la Vmax del panel, que
    vuelven al abrir después unas cuentas (:func:`calibration_after_load`)."""
    path = Path(path)
    if previous and previous.get("source") == "embedded":
        # Varios procesados seguidos: lo que vuelve es lo de antes del primero.
        replaced = previous.get("replaced_calibration")
        vmax_before = previous.get("replaced_vmax", vmax_before)
    else:
        replaced = dict(previous) if previous else None
    return {
        "source": "embedded",
        "calibration_sample": path.stem,
        "velocity_calibrated": float(file_vmax),
        "isomer_shift": (previous or {}).get("isomer_shift"),
        "isomer_shift_uncertainty": (previous or {}).get("isomer_shift_uncertainty"),
        "calibration_file_name": path.name,
        "calibration_file_path": str(path),
        "replaced_calibration": replaced,
        "replaced_vmax": None if vmax_before is None else float(vmax_before),
    }


def missing_calibration_reason(choice) -> str:
    """Por qué un equipo no da calibración para un fichero:
    ``"none"`` (no tiene ninguna), ``"no_date"`` (la regla es por fecha y el
    fichero no la tiene) o ``"none_before"`` (ninguna de esa fecha o antes)."""
    if choice.rule in ("latest", "manual"):
        return "none"
    return "no_date" if choice.date is None else "none_before"


def resolve_session_spectrum(file_path: str | Path | None,
                             session_path: str | Path) -> Path | None:
    """Fichero del espectro de una sesión que se ha movido de sitio.

    Si ``file_path`` existe, ese. Si no (sesión de otro ordenador o carpeta
    movida), el fichero del mismo nombre junto a la sesión, también con otras
    mayúsculas (``calibration.ADT`` → ``calibration.adt``). ``None`` si no hay.
    """
    if not file_path:
        return None
    original = Path(file_path)
    folder = Path(session_path).parent
    if original.is_absolute() and original.exists():
        return original
    if not original.is_absolute() and (folder / original).exists():
        return folder / original
    name = original.name.lower()
    try:
        for candidate in folder.iterdir():
            if candidate.is_file() and candidate.name.lower() == name:
                return candidate
    except OSError:
        return None
    return original if original.exists() else None


# ── Abrir un fichero ──────────────────────────────────────────────────────
@dataclass
class OpenedSpectrum:
    """Un fichero leído y, si se abrió con un equipo, su calibración elegida.

    ``choice`` es ``None`` sin equipo o si el fichero trae su propio eje de
    velocidad; ``calibration`` es el ``calibration_info`` del equipo o ``None``
    si no hay calibración aplicable (``choice.record is None``).
    """
    path: Path
    imported: ImportedSpectrum
    instrument: str | None = None
    choice: object | None = None
    calibration: dict | None = None

    @property
    def has_velocity_axis(self) -> bool:
        return self.imported.x_kind == "velocity"

    @property
    def file_vmax(self) -> float:
        """Vmax aproximada del eje propio (máximo de |v|)."""
        x = np.asarray(self.imported.x, dtype=float)
        return float(np.max(np.abs(x))) if x.size else 12.0


def open_spectrum(path: str | Path, hints: ImportHints | None = None, *,
                  library=None, instrument: str | None = None,
                  calibration_id: str | None = None) -> OpenedSpectrum:
    """Lee ``path`` y elige la calibración de ``instrument`` (si se da).

    Por canales, solo se aceptan cuentas (``ValueError`` si no). Las
    correcciones de lectura son ``hints`` tal cual: quien abre con un equipo
    pasa las suyas.
    """
    from mossbauer_i18n import tr
    path = Path(path)
    imported = read_spectrum_file(path, hints)
    opened = OpenedSpectrum(path=path, imported=imported, instrument=instrument)
    if opened.has_velocity_axis:
        return opened
    if not imported.is_counts:
        raise ValueError(tr("load.not_channel_counts", name=path.name,
                            default="{name} does not contain counts per channel."))
    if instrument and library is not None:
        opened.choice = library.choose_calibration(instrument, imported, path,
                                                   record_id=calibration_id)
        opened.calibration = library.calibration_info(instrument, opened.choice)
    return opened


def calibration_after_load(previous: dict | None, opened: OpenedSpectrum,
                           vmax_before: float | None = None) -> dict | None:
    """Calibración vigente tras cargar ``opened`` (ver la prioridad del módulo).

    ``vmax_before`` es la Vmax en uso al abrirlo (la que se recupera si un
    fichero con eje propio no sustituía ninguna calibración)."""
    if opened.has_velocity_axis:
        return embedded_calibration_info(opened.path, opened.file_vmax, previous,
                                         vmax_before)
    if opened.calibration is not None:
        return opened.calibration
    if previous and previous.get("source") == "embedded":
        return previous.get("replaced_calibration")
    return previous
