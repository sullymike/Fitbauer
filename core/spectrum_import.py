"""Lector genérico de espectros Mössbauer en texto (cualquier equipo).

No conoce formatos concretos: localiza el bloque de datos numéricos dentro del
fichero (lo anterior es cabecera y lo posterior pie), detecta separador y coma
decimal, deduce el papel de cada columna (canal, velocidad, intensidad, error)
y el tipo de intensidad (cuentas, transmisión o absorción, en fracción o %).

Toda deducción puede corregirse con :class:`ImportHints`, que es serializable:
guardada por equipo, hace de «perfil de importación», de modo que cada
espectrómetro (los que sean) se configura una vez.

El lector **no dobla ni ordena**: devuelve los datos en el orden del fichero.
Decidir si se doblan es un paso posterior y explícito.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from mossbauer_i18n import tr

#: Papeles posibles de una columna.
COLUMN_ROLES = ("channel", "velocity", "y", "sigma", "ignore")

#: Tipos de intensidad y su conversión a transmisión relativa ``T``.
Y_KINDS = ("counts", "transmission", "transmission_percent",
           "absorption", "absorption_percent", "transmission_deviation",
           "transmission_deviation_percent")

#: Separadores: espacios/tabuladores/punto y coma, o coma.
SEPARATORS = {"whitespace": re.compile(r"[\s;]+"),
              "comma": re.compile(r"\s*,\s*")}

# Orden de preferencia en caso de empate: «1,5» como dos campos (canal,
# cuentas) es más habitual que una sola columna con coma decimal.
_DIALECTS = (("whitespace", "."), ("comma", "."), ("whitespace", ","))

# Número completo (admite exponente Fortran con D).
_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?$")
_KEY_VALUE = re.compile(r"^\s*[#;!%*$]*\s*([A-Za-z][\w .()/\-]{0,40}?)\s*[:=]\s*(\S.*?)\s*$")
_DATE = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b")
_XML_DATA = re.compile(r"<data\b([^>]*)>(.*?)(?:</data>|$)", re.S | re.I)
_XML_ATTR = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\"")
_XML_TAG = re.compile(r"<(\w+)\b[^>]*>([^<>]+)</\1>")


@dataclass
class ImportHints:
    """Correcciones a la detección automática (``None`` = automático).

    ``data_start``/``data_end`` son índices de línea (0-based, fin exclusivo).
    ``columns`` da un papel de :data:`COLUMN_ROLES` a cada columna del bloque.
    """
    data_start: int | None = None
    data_end: int | None = None
    separator: str | None = None
    decimal: str | None = None
    columns: tuple[str, ...] | None = None
    y_kind: str | None = None
    row_major: bool | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["columns"] is not None:
            d["columns"] = list(d["columns"])
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict | None) -> "ImportHints":
        data = dict(data or {})
        if data.get("columns") is not None:
            data["columns"] = tuple(data["columns"])
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


@dataclass
class ImportedSpectrum:
    """Resultado de la lectura, sin doblar y en el orden del fichero.

    ``x_kind`` es ``"channel"`` (``y`` son intensidades por canal; ``x`` el nº
    de canal) o ``"velocity"`` (``x`` en mm/s). ``y`` es la intensidad tal como
    viene; :meth:`transmission` la pasa a transmisión relativa.
    """
    x_kind: str
    x: np.ndarray
    y: np.ndarray
    y_kind: str
    sigma: np.ndarray | None
    sigma_source: str                 # "poisson" | "column" | "estimated"
    data_start: int
    data_end: int
    separator: str
    decimal: str
    columns: tuple[str, ...]
    row_major: bool = False
    header: list[str] = field(default_factory=list)
    footer: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    dates: list[str] = field(default_factory=list)
    velocity_turning_points: int = 0
    warnings: list[str] = field(default_factory=list)
    source_format: str = "text"       # "text" | "ws5"

    @property
    def is_counts(self) -> bool:
        return self.y_kind == "counts"

    def hints(self) -> ImportHints:
        """Lo detectado, como hints: base de un perfil de importación."""
        return ImportHints(data_start=self.data_start, data_end=self.data_end,
                           separator=self.separator, decimal=self.decimal,
                           columns=self.columns, y_kind=self.y_kind,
                           row_major=self.row_major)

    def transmission(self) -> tuple[np.ndarray, np.ndarray]:
        """Transmisión relativa ``T`` (línea base ~1) y su σ.

        Para cuentas se normaliza por la línea base (percentil 90), como hace
        el resto del programa; la σ es la de Poisson escalada igual.
        """
        t, scale = _to_transmission(self.y, self.y_kind)
        sigma = self.sigma
        if sigma is None:
            sigma = _estimate_noise(t) * np.ones_like(t)
        else:
            sigma = np.abs(sigma) * scale
        if self.y_kind == "counts":
            norm = float(np.percentile(t, 90)) or 1.0
            return t / norm, sigma / norm
        return t, sigma


# ── API pública ───────────────────────────────────────────────────────────────

def read_text(path: str | Path) -> str:
    """Texto de un fichero de cualquier equipo: UTF-8/16 o, si no, Latin-1."""
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_spectrum_file(path: str | Path,
                       hints: ImportHints | None = None) -> ImportedSpectrum:
    """Lee un espectro de un fichero de texto (ver :func:`parse_spectrum_text`)."""
    try:
        return parse_spectrum_text(read_text(path), hints)
    except ValueError as exc:
        raise ValueError(f"{Path(path).name}: {exc}") from exc


def parse_spectrum_text(text: str,
                        hints: ImportHints | None = None) -> ImportedSpectrum:
    """Lee un espectro de un texto con cabecera y pie arbitrarios."""
    hints = hints or ImportHints()
    lines = text.splitlines()
    xml = _XML_DATA.search(text)
    if xml and hints.data_start is None:
        return _parse_ws5(text, lines, xml, hints)

    block = _find_block(lines, hints)
    if block is None:
        raise ValueError(tr("load.no_data_block",
                            default="No numeric data block was found."))
    start, end, sep, dec, rows = block
    header, footer = lines[:start], lines[end:]
    data = np.array(rows, dtype=float)

    # Una sola columna cuyo primer valor es el nº de valores que siguen: es
    # el recuento de canales de la cabecera, no un dato.
    if (hints.data_start is None and data.shape[1] == 1 and data.shape[0] > 2
            and data[0, 0] == data.shape[0] - 1):
        header = lines[:start + 1]
        data = data[1:]
        start += 1

    res = _interpret(data, hints)
    meta, dates = _metadata(header + footer)
    res.update(data_start=start, data_end=end, separator=sep, decimal=dec,
               header=header, footer=footer, metadata=meta, dates=dates)
    return ImportedSpectrum(**res)


# ── Bloque de datos ───────────────────────────────────────────────────────────

def _tokens(line: str, sep: str, dec: str) -> list[float] | None:
    """Campos numéricos de una línea, o ``None`` si alguno no es un número."""
    parts = [p for p in SEPARATORS[sep].split(line.strip()) if p]
    if not parts:
        return None
    out = []
    for p in parts:
        if dec == ",":
            if "." in p:
                return None
            p = p.replace(",", ".")
        if not _NUMBER.match(p):
            return None
        out.append(float(p.replace("d", "e").replace("D", "e")))
    return out


def _runs(lines: list[str], sep: str, dec: str):
    """Tramos de líneas numéricas con igual nº de campos (blancos neutros)."""
    start = None
    width = 0
    rows: list[list[float]] = []
    last = -1
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        vals = _tokens(line, sep, dec)
        if vals is not None and start is not None and len(vals) == width:
            rows.append(vals)
            last = i
            continue
        if start is not None:
            yield start, last + 1, rows
            start = None
        if vals is not None:
            start, width, rows, last = i, len(vals), [vals], i
    if start is not None:
        yield start, last + 1, rows


def _find_block(lines: list[str], hints: ImportHints):
    dialects = [(s, d) for s, d in _DIALECTS
                if hints.separator in (None, s) and hints.decimal in (None, d)]
    if not dialects and hints.separator and hints.decimal:
        dialects = [(hints.separator, hints.decimal)]
    best = None
    for sep, dec in dialects:
        if hints.data_start is not None:
            a = hints.data_start
            b = len(lines) if hints.data_end is None else hints.data_end
            rows = [v for v in (_tokens(l, sep, dec) for l in lines[a:b] if l.strip())
                    if v is not None]
            if rows:
                width = max(set(map(len, rows)), key=[len(r) for r in rows].count)
                rows = [r for r in rows if len(r) == width]
                cand = (a, b, sep, dec, rows)
                if best is None or len(rows) > len(best[4]):
                    best = cand
            continue
        for a, b, rows in _runs(lines, sep, dec):
            if best is None or len(rows) > len(best[4]):
                best = (a, b, sep, dec, rows)
    if best is None or len(best[4]) < 2:
        return None
    return best


def _parse_ws5(text: str, lines: list[str], m: re.Match,
               hints: ImportHints) -> ImportedSpectrum:
    """WS5 (XML de WissEl): cuentas dentro de ``<data>``."""
    values = [float(v) for v in re.findall(r"[-+]?\d+(?:\.\d+)?", m.group(2))]
    if len(values) < 2:
        raise ValueError(tr("load.no_data_block",
                            default="No numeric data block was found."))
    start = text.count("\n", 0, m.start(2))
    end = text.count("\n", 0, m.end(2)) + 1
    meta = {f"data.{k}": v for k, v in _XML_ATTR.findall(m.group(1))}
    # Etiquetas simples de cabecera/pie; el bloque <data> (o cualquier
    # contenido de varias líneas) no es un metadato.
    meta.update({k: v.strip() for k, v in _XML_TAG.findall(text)
                 if k.lower() != "data" and "\n" not in v.strip()})
    y = np.array(values)
    kind = hints.y_kind or "counts"
    return ImportedSpectrum(
        x_kind="channel", x=np.arange(1, y.size + 1, dtype=float), y=y,
        y_kind=kind, sigma=np.sqrt(np.maximum(y, 1.0)) if kind == "counts" else None,
        sigma_source="poisson" if kind == "counts" else "estimated",
        data_start=start, data_end=end, separator="whitespace", decimal=".",
        columns=("y",), header=lines[:start], footer=lines[end:],
        metadata=meta, dates=_DATE.findall(text[:m.start()]), source_format="ws5")


# ── Interpretación de columnas ────────────────────────────────────────────────

def _is_integer(col: np.ndarray) -> bool:
    return bool(np.all(np.abs(col - np.round(col)) < 1e-9))


def _is_channel(col: np.ndarray) -> bool:
    return col.size > 2 and _is_integer(col) and bool(np.all(np.diff(col) == 1))


def _is_velocity(col: np.ndarray) -> bool:
    """Eje de velocidad: mm/s, no entero y suave (una o dos ramas del barrido)."""
    if col.size < 3 or _is_integer(col):
        return False
    rng = float(np.ptp(col))
    if not (0.5 <= rng and np.max(np.abs(col)) < 100.0):
        return False
    steps = np.abs(np.diff(col))
    return float(np.max(steps)) < 0.3 * rng and float(np.median(steps)) < 0.05 * rng


def _counts_like(col: np.ndarray) -> bool:
    return bool(np.all(col >= 0) and np.median(col) > 20)


def _guess_columns(data: np.ndarray) -> tuple[tuple[str, ...], bool]:
    """Papel de cada columna y si las cuentas van por filas (varias por línea)."""
    ncol = data.shape[1]
    if ncol == 1:
        return ("y",), False
    cols = [data[:, j] for j in range(ncol)]
    # Filas indexadas: «canal_inicial  c1 c2 … ck» con el índice avanzando k.
    if ncol >= 3 and _is_integer(cols[0]) and data.shape[0] > 1:
        step = np.diff(cols[0])
        if np.all(step == ncol - 1) and all(_counts_like(c) for c in cols[1:]):
            return ("channel",) + ("y",) * (ncol - 1), True
    roles = ["ignore"] * ncol
    vel = next((j for j, c in enumerate(cols) if _is_velocity(c)), None)
    chan = next((j for j, c in enumerate(cols) if j != vel and _is_channel(c)), None)
    if vel is None and chan is None and ncol >= 3 and all(map(_counts_like, cols)):
        return ("y",) * ncol, True            # varias cuentas por línea
    if vel is not None:
        roles[vel] = "velocity"
    if chan is not None:
        roles[chan] = "channel"
    rest = [j for j in range(ncol) if roles[j] == "ignore"]
    if rest:
        roles[rest[0]] = "y"
        y = cols[rest[0]]
        if len(rest) > 1:
            s = cols[rest[1]]
            if np.all(s > 0) and np.median(s) < 0.5 * np.median(np.abs(y)) + 1e-12:
                roles[rest[1]] = "sigma"
    return tuple(roles), False


def _guess_y_kind(y: np.ndarray) -> str:
    p50, p90 = np.percentile(y, [50, 90])
    ymin, ymax = float(np.min(y)), float(np.max(y))
    if 95.0 <= p90 <= 105.0 and ymax <= 110.0 and not _is_integer(y):
        return "transmission_percent"
    if ymin >= 0 and p50 > 20:
        return "counts"
    if 0.5 <= p90 <= 1.5:
        return "transmission"
    span = max(abs(ymin), abs(ymax)) or 1.0
    if abs(p50) < 0.2 * span:                  # línea base en cero
        if abs(ymin) > abs(ymax):
            # T − 1, picos hacia abajo. Más allá de ±1 no puede ser una
            # fracción: es en % (WMOSS, «% absorbance»: T = 1 + y/100).
            return ("transmission_deviation_percent" if span > 1.0
                    else "transmission_deviation")
        return "absorption" if ymax <= 1.0 else "absorption_percent"
    if ymin < 0 and abs(ymin) > abs(ymax):
        # Picos hacia abajo con la línea base desplazada (p. ej. la traza de
        # un subespectro de WMOSS, dibujada por debajo de cero): T − 1, no
        # cuentas, que nunca son negativas.
        return ("transmission_deviation_percent" if span > 1.0
                else "transmission_deviation")
    return "counts"


def _interpret(data: np.ndarray, hints: ImportHints) -> dict:
    warnings: list[str] = []
    ncol = data.shape[1]
    if hints.columns is not None:
        if len(hints.columns) != ncol:
            raise ValueError(tr(
                "load.columns_mismatch", n=ncol, m=len(hints.columns),
                default="The data block has {n} columns but the profile defines {m}."))
        bad = set(hints.columns) - set(COLUMN_ROLES)
        if bad:
            raise ValueError(f"unknown column roles: {sorted(bad)}")
        roles = tuple(hints.columns)
        row_major = bool(hints.row_major)
    else:
        roles, row_major = _guess_columns(data)
        if hints.row_major is not None:
            row_major = hints.row_major
    if "y" not in roles:
        raise ValueError(tr("load.no_intensity_column",
                            default="No intensity column was found."))

    if row_major:
        ycols = [j for j, r in enumerate(roles) if r == "y"]
        y = data[:, ycols].ravel()
        first = data[0, roles.index("channel")] if "channel" in roles else 1.0
        x = first + np.arange(y.size, dtype=float)
        x_kind, sigma = "channel", None
    else:
        y = data[:, roles.index("y")]
        sigma = data[:, roles.index("sigma")] if "sigma" in roles else None
        if "velocity" in roles:
            x_kind, x = "velocity", data[:, roles.index("velocity")]
        elif "channel" in roles:
            x_kind, x = "channel", data[:, roles.index("channel")]
        else:
            x_kind, x = "channel", np.arange(1, y.size + 1, dtype=float)

    y_kind = hints.y_kind or _guess_y_kind(y)
    if y_kind not in Y_KINDS:
        raise ValueError(f"unknown intensity kind: {y_kind}")
    if sigma is not None:
        sigma_source = "column"
    elif y_kind == "counts":
        sigma, sigma_source = np.sqrt(np.maximum(y, 1.0)), "poisson"
    else:
        sigma_source = "estimated"
        warnings.append("sigma_estimated")
    if y_kind == "absorption" and hints.y_kind is None:
        warnings.append("absorption_units_ambiguous")
    if y_kind == "counts" and float(np.median(y)) < 1000:
        warnings.append("low_counts")

    turning = 0
    if x_kind == "velocity":
        d = np.sign(np.diff(x))
        d = d[d != 0]
        turning = int(np.count_nonzero(d[1:] != d[:-1]))
    if y.size < 10:
        raise ValueError(tr("load.too_few_values", n=y.size,
                            default="Only {n} data values were found; at least 10 are required."))
    return dict(x_kind=x_kind, x=np.asarray(x, float), y=np.asarray(y, float),
                y_kind=y_kind, sigma=sigma, sigma_source=sigma_source,
                columns=roles, row_major=row_major,
                velocity_turning_points=turning, warnings=warnings)


# ── Conversión y ruido ────────────────────────────────────────────────────────

def _to_transmission(y: np.ndarray, kind: str) -> tuple[np.ndarray, float]:
    """``T`` a partir de la intensidad y el factor que escala su σ."""
    if kind in ("counts", "transmission"):
        return y.astype(float), 1.0
    if kind == "transmission_percent":
        return y / 100.0, 0.01
    if kind == "absorption":
        return 1.0 - y, 1.0
    if kind == "absorption_percent":
        return 1.0 - y / 100.0, 0.01
    if kind == "transmission_deviation":
        return 1.0 + y, 1.0
    if kind == "transmission_deviation_percent":
        return 1.0 + y / 100.0, 0.01
    raise ValueError(f"unknown intensity kind: {kind}")


def _estimate_noise(t: np.ndarray) -> float:
    """σ del ruido a partir de segundas diferencias (robusto a las líneas).

    Para ruido blanco, var(Δ²t) = 6σ²; la MAD ignora los puntos en flancos.
    """
    if t.size < 5:
        return float(np.std(t)) or 1.0
    d2 = np.diff(t, 2)
    mad = float(np.median(np.abs(d2 - np.median(d2))))
    sigma = 1.4826 * mad / np.sqrt(6.0)
    return sigma if sigma > 0 else (float(np.std(d2)) / np.sqrt(6.0) or 1.0)


# ── Metadatos de cabecera y pie ───────────────────────────────────────────────

def _metadata(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    meta: dict[str, str] = {}
    dates: list[str] = []
    for line in lines:
        m = _KEY_VALUE.match(line)
        if m:
            meta.setdefault(m.group(1).strip(), m.group(2))
        dates.extend(_DATE.findall(line))
    return meta, dates


# ── Fecha de medida ──────────────────────────────────────────────────────────

DATE_ORDERS = ("dmy", "mdy")

_MONTHS = {m: i for i, names in enumerate((
    ("jan", "ene"), ("feb",), ("mar",), ("apr", "abr"), ("may",), ("jun",),
    ("jul",), ("aug", "ago"), ("sep", "set"), ("oct",), ("nov",), ("dec", "dic")), 1)
    for m in names}
_ISO_DATE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_NUM_DATE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b")
_TEXT_DATE = re.compile(
    r"\b(?:(\d{1,2})[\s\-]+([A-Za-z]{3,9})\.?[\s\-,]+(\d{4})"
    r"|([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4}))\b")


def _make_date(y: int, m: int, d: int):
    import datetime as _dt
    if y < 100:
        y += 2000 if y < 70 else 1900
    try:
        return _dt.date(y, m, d)
    except ValueError:
        return None


def parse_date_text(text: str, date_order: str = "dmy"):
    """Primera fecha válida de un texto (``datetime.date`` o ``None``).

    Reconoce ISO (``2025-03-14``), numéricas (``14/03/2025``, ``03.14.25``) y
    con el mes en letra (``14 Mar 2025``, ``March 14, 2025``; inglés o
    español). En las numéricas ambiguas (día y mes ≤ 12) decide
    ``date_order``: ``"dmy"`` o ``"mdy"``; si un campo pasa de 12, manda él.
    """
    found = []
    for m in _ISO_DATE.finditer(text):
        found.append((m.start(), _make_date(int(m[1]), int(m[2]), int(m[3]))))
    for m in _NUM_DATE.finditer(text):
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if a > 12:
            d, mo = a, b
        elif b > 12:
            mo, d = a, b
        elif date_order == "mdy":
            mo, d = a, b
        else:
            d, mo = a, b
        found.append((m.start(), _make_date(y, mo, d)))
    for m in _TEXT_DATE.finditer(text):
        if m[1]:
            d, name, y = m[1], m[2], m[3]
        else:
            name, d, y = m[4], m[5], m[6]
        mo = _MONTHS.get(name[:3].lower())
        if mo:
            found.append((m.start(), _make_date(int(y), mo, int(d))))
    found = [f for f in found if f[1] is not None]
    return min(found, key=lambda f: f[0])[1] if found else None


def intensity_column_choices(spectrum: "ImportedSpectrum") -> list[int]:
    """Columnas que pueden ser la intensidad de un fichero en velocidad.

    Las que no son eje ni σ: la elegida por el lector (``"y"``) y las
    descartadas (``"ignore"``), p. ej. el ajuste total y los subespectros que
    WinNormos escribe junto a los datos.
    """
    return [i for i, role in enumerate(spectrum.columns) if role in ("y", "ignore")]


def with_intensity_column(spectrum: "ImportedSpectrum", index: int) -> tuple[str, ...]:
    """Papeles de columna con ``index`` como intensidad y el resto de
    candidatas descartadas (para :class:`ImportHints`)."""
    return tuple("y" if i == index else ("ignore" if role in ("y", "ignore") else role)
                 for i, role in enumerate(spectrum.columns))


def axis_referred_to_alpha_fe(velocity: np.ndarray, iso_ref: float | None,
                              tol: float = 0.03) -> bool:
    """¿Parece un eje con el α-Fe en 0 (WMOSS, WinNormos, NORMOS…)?

    Un eje respecto a la fuente es simétrico; uno referido al α-Fe está
    desplazado en −δ(α-Fe). Se compara el centro del eje con ``−iso_ref``.
    """
    if iso_ref is None or abs(iso_ref) < tol:
        return False
    v = np.asarray(velocity, dtype=float)
    if v.size < 2:
        return False
    center = 0.5 * (float(np.min(v)) + float(np.max(v)))
    return abs(center + iso_ref) < tol


def measurement_date(spectrum: "ImportedSpectrum", path: str | Path | None = None,
                     date_order: str = "dmy"):
    """Fecha de medida: ``(fecha, origen)``, con origen ``"header"`` o ``"file"``.

    Se busca en la cabecera y el pie (primero en las líneas que hablan de
    fecha); si no hay, la fecha de modificación del fichero, que es solo una
    aproximación (una copia la cambia). ``(None, None)`` si no hay ninguna.
    """
    import datetime as _dt
    lines = list(spectrum.header) + list(spectrum.footer)
    keyed = [l for l in lines if re.search(r"date|fecha|datum|time|start", l, re.I)]
    for group in (keyed, lines):
        found = parse_date_text("\n".join(group), date_order)
        if found is not None:
            return found, "header"
    if path is not None:
        try:
            return _dt.date.fromtimestamp(Path(path).stat().st_mtime), "file"
        except OSError:
            pass
    return None, None
