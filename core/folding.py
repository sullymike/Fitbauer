"""Funciones puras de carga (.ws5/.adt/Normos) y folding.

Todas son ``module-level`` y no dependen de ningún front-end: pueden ser
importadas por la GUI Qt o por scripts CLI.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

# ── Cargador de espectros ya doblados en espacio de velocidad ─────────────────

#: Cuentas máximas usadas al convertir transmisión normalizada (≤1) a cuentas.
_CSV_MAX_COUNT = 2_000_000


def load_velocity_csv(path: str | Path) -> dict:
    """Carga un espectro Mössbauer ya doblado en formato CSV/TXT (espacio velocidad).

    Soporta:
    - Separadores: coma, tabulador o espacio(s).
    - Líneas de comentario o cabecera: se ignoran si empiezan por ``#`` o si
      algún campo no es numérico.
    - Detección automática de transmisión normalizada: si todos los valores de
      la columna 2 son ≤ 1.0, se interpreta como transmisión y se escala a
      ``round(_CSV_MAX_COUNT * col2)``.
    - El eje de velocidad se devuelve ordenado de menor a mayor.

    Parameters
    ----------
    path:
        Ruta al fichero CSV/TXT/DAT/EXP.

    Returns
    -------
    dict con claves:
        ``"velocity"`` : np.ndarray — velocidades en mm/s (ordenadas ascendente).
        ``"y"``        : np.ndarray — cuentas (float).
        ``"source"``   : ``"csv"``.

    Raises
    ------
    ValueError
        Si se encuentran menos de 10 puntos de datos válidos.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    velocities: list[float] = []
    ys: list[float] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Sustituir comas y tabuladores por espacio para facilitar el split.
        parts = re.split(r"[,\t\s]+", stripped)
        if len(parts) < 2:
            continue
        try:
            v = float(parts[0])
            y = float(parts[1])
        except ValueError:
            # Línea de cabecera con texto no numérico → ignorar.
            continue
        velocities.append(v)
        ys.append(y)

    if len(velocities) < 10:
        raise ValueError(
            f"Se encontraron solo {len(velocities)} puntos válidos en {path}; "
            "se requieren al menos 10."
        )

    vel = np.array(velocities, dtype=float)
    y_arr = np.array(ys, dtype=float)

    # Detección de columnas intercambiadas: si col0 (velocidad) tiene todos los
    # valores > 100 y col1 (y) tiene todos los valores en [-20, 20], es probable
    # que el fichero tenga intensidad en la primera columna y velocidad en la segunda.
    if np.all(vel > 100.0) and np.all((y_arr >= -20.0) & (y_arr <= 20.0)):
        raise ValueError(
            "El fichero parece tener las columnas en orden inverso (intensidad, velocidad). "
            "Invierte las columnas o usa un fichero con velocidad en la primera columna."
        )

    # Convertir transmisión normalizada a cuentas si todos los valores son ≤ 1.
    if float(np.max(y_arr)) <= 1.0:
        y_arr = np.round(_CSV_MAX_COUNT * y_arr).astype(float)

    # Ordenar por velocidad ascendente.
    order = np.argsort(vel)
    vel = vel[order]
    y_arr = y_arr[order]

    # Validación de rango de velocidades.
    v_range = float(vel[-1] - vel[0])
    if v_range < 1.0:
        raise ValueError(
            f"Rango de velocidades demasiado estrecho ({v_range:.3f} mm/s). "
            "Se requiere al menos 1 mm/s de rango."
        )

    # Deduplicación de velocidades: si dos velocidades consecutivas son iguales
    # (o más cercanas que 1e-9), se promedian sus valores y se conserva uno.
    if np.any(np.diff(vel) < 1e-9):
        unique_vel: list[float] = []
        unique_y: list[float] = []
        i = 0
        while i < len(vel):
            j = i + 1
            while j < len(vel) and (vel[j] - vel[i]) < 1e-9:
                j += 1
            unique_vel.append(float(np.mean(vel[i:j])))
            unique_y.append(float(np.mean(y_arr[i:j])))
            i = j
        vel = np.array(unique_vel, dtype=float)
        y_arr = np.array(unique_y, dtype=float)

    return {"velocity": vel, "y": y_arr, "source": "csv"}


def read_ws5_counts(path: Path) -> np.ndarray:
    """Lee cuentas de ficheros WS5 XML o ADT antiguos sin cabecera.

    Los WS5 modernos tienen un bloque <data>...</data>. Algunos ficheros antiguos
    descargados de la web son ADT: solo una lista de cuentas, sin XML ni cabecera.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<data[^>]*>(.*?)</data>", text, re.S | re.I)
    source = m.group(1) if m else text
    counts = np.array([float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", source)])
    if counts.size < 2:
        raise ValueError(f"No se encontraron cuentas suficientes en {path}")
    return counts


def _number_re() -> str:
    return r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?"


def read_normos_folding_point(path: Path) -> float | None:
    """Lee el 'Final folding point' de Normos si existe y lo pasa a centro interno.

    Algunas versiones de Normos reportan el PFP en convención de espectro
    completo (~511 para 512 canales) y otras en convención de semiespecro
    (~256). Se distinguen por el valor: >= 400 → espectro completo (÷2);
    < 400 → semiespecro (usar tal cual).
    """
    res = path.with_suffix(".RES")
    if not res.exists():
        res = path.with_suffix(".res")
    if not res.exists():
        return None
    text = res.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"Final folding point\s*=\s*(" + _number_re() + ")", text, re.I)
    if not matches:
        return None
    v = float(matches[-1].replace("D", "E").replace("d", "E"))
    return 0.5 * v if v >= 400.0 else v


def read_normos_plt_velocity(path: Path) -> float | None:
    """Lee Vmax del .PLT asociado si existe."""
    plt = path.with_suffix(".PLT")
    if not plt.exists():
        plt = path.with_suffix(".plt")
    if not plt.exists():
        return None
    text = plt.read_text(encoding="utf-8", errors="replace")
    nums = [float(x.replace("D", "E").replace("d", "E")) for x in re.findall(_number_re(), text)]
    # El primer número suele venir de la cabecera "2d"; después hay bloques de 256.
    if len(nums) % 256 == 1:
        nums = nums[1:]
    if len(nums) >= 256:
        return float(max(abs(min(nums[:256])), abs(max(nums[:256]))))
    return None


def read_normos_sidecar_params(path: Path) -> dict[str, float]:
    """Extrae valores finales de Normos (.RES) y parámetros fijos del .JOB."""
    params: dict[str, float] = {}
    res = path.with_suffix(".RES")
    if not res.exists():
        res = path.with_suffix(".res")
    if res.exists():
        text = res.read_text(encoding="utf-8", errors="replace")
        final: dict[str, float] = {}
        for name in ("WID", "ARE", "ISO", "QUA", "BHF"):
            m = re.search(rf"\b{name}\s+({_number_re()})\s+({_number_re()})", text, re.I)
            if m:
                final[name.upper()] = float(m.group(2).replace("D", "E").replace("d", "E"))
        if "ISO" in final:
            params["s1_delta"] = final["ISO"]
        if "BHF" in final:
            params["s1_bhf"] = final["BHF"]
        if "QUA" in final:
            params["s1_quad"] = final["QUA"]
        if "WID" in final:
            params["s1_gamma1"] = max(0.06, final["WID"])
            params["s1_gamma2"] = 1.0
            params["s1_gamma3"] = 1.0
        if "ARE" in final and "s1_gamma1" in params:
            weight_sum = 2.0 * (3.0 + 2.0 + 1.0)
            params["s1_depth"] = max(0.0, min(0.30, final["ARE"] / (np.pi * params["s1_gamma1"] * weight_sum)))
    job = path.with_suffix(".JOB")
    if not job.exists():
        job = path.with_suffix(".job")
    if job.exists():
        text = job.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\bVMAX\s*=\s*(" + _number_re() + ")", text, re.I)
        if m:
            params["vmax"] = abs(float(m.group(1).replace("D", "E").replace("d", "E")))
        m = re.search(r"\bQUA\(1\)\s*=\s*(" + _number_re() + ")", text, re.I)
        if m and "s1_quad" not in params:
            params["s1_quad"] = float(m.group(1).replace("D", "E").replace("d", "E"))
    return params


def interp_channel_1based(counts: np.ndarray, channel: float) -> float:
    """Interpolación lineal C(channel) con canales 1..N; extrapola en bordes.

    Normos genera siempre NP=N/2 puntos doblados. Cuando el punto de doblado no
    deja 256 pares enteros completos, el primer/último punto se obtiene por una
    extrapolación mínima en el borde; esto evita perder un canal para centros
    como 255.5 en espectros de 512 canales.
    """
    n = counts.size
    if channel < 1.0:
        return float(counts[0] + (channel - 1.0) * (counts[1] - counts[0]))
    if channel >= float(n):
        return float(counts[-1] + (channel - float(n)) * (counts[-1] - counts[-2]))
    lo = int(np.floor(channel))
    frac = channel - lo
    if frac < 1e-12:
        return float(counts[lo - 1])
    return float((1.0 - frac) * counts[lo - 1] + frac * counts[lo])


def fold_integer_or_half(counts: np.ndarray, center: float) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Dobla a N/2 puntos al estilo Normos.

    Canales numerados 1..N. El resultado va de velocidad negativa a positiva,
    desde el par exterior izquierdo hacia el centro y de nuevo hacia el exterior
    derecho. Para centros semienteros ordinarios coincide con el promedio de
    pares simétricos; en los bordes usa interpolación/extrapolación lineal.
    """
    n = counts.size
    n_out = n // 2
    rows: list[tuple[int, int, float]] = []
    for j in range(n_out):
        distance = j + 0.5
        left_ch = center - distance
        right_ch = center + distance
        folded = 0.5 * (interp_channel_1based(counts, left_ch) + interp_channel_1based(counts, right_ch))
        rows.append((int(round(left_ch)), int(round(right_ch)), folded))
    return np.array([r[2] for r in rows], dtype=float), [(r[0], r[1]) for r in rows]


def chi2_for_center(counts: np.ndarray, center: float) -> tuple[float, int]:
    folded, pairs = fold_integer_or_half(counts, center)
    chi2 = 0.0
    for left, right in pairs:
        if not (1 <= left <= counts.size and 1 <= right <= counts.size):
            continue
        d = counts[left - 1] - counts[right - 1]
        chi2 += d * d
    return chi2, len(pairs)


def find_best_integer_or_half_center(counts: np.ndarray, cmin: float = 250.5, cmax: float = 262.5) -> float:
    """Busca el folding point con interpolación subcanal.

    Normos no se queda en canales enteros/semienteros: primero localiza el
    mínimo de chi² en una malla y después interpola el mínimo. Internamente esta
    GUI usa el centro de simetría (≈255.77 para un "upper folding point" Normos
    ≈511.55 en 512 canales), por eso el número Normos es aproximadamente el
    doble del mostrado aquí.
    """
    candidates = np.arange(cmin, cmax + 1e-9, 0.5)
    values: list[tuple[float, float]] = []
    for center in candidates:
        chi2, n_pairs = chi2_for_center(counts, float(center))
        if n_pairs:
            values.append((float(center), chi2 / n_pairs))
    if not values:
        return 0.5 * counts.size
    best_i = min(range(len(values)), key=lambda i: values[i][1])
    if 0 < best_i < len(values) - 1:
        xm, ym = values[best_i - 1]
        x0, y0 = values[best_i]
        xp, yp = values[best_i + 1]
        den = ym - 2.0 * y0 + yp
        if den > 0:
            step = x0 - xm
            xv = x0 + 0.5 * step * (ym - yp) / den
            if xm <= xv <= xp:
                return float(xv)
    return values[best_i][0]


# ── Doblado + normalización + eje de velocidad (compartido GUI/headless) ──────
# Fuente única usada por la GUI Qt y por core.session (controlador headless),
# para que ambos doblen, normalicen y construyan el eje exactamente igual.

EDGE_TRIM_DEFAULT = 1


def fold_and_normalize(counts: np.ndarray, center: float,
                       edge_trim: int = EDGE_TRIM_DEFAULT
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Dobla, recorta los bordes y normaliza el espectro.

    Devuelve ``(folded, sigma, y, norm)`` con la línea base normalizada a ~1 y
    ``sigma`` el ruido Poisson normalizado. ``edge_trim`` recorta el primer y
    último canal del espectro doblado (canales de borde menos fiables).
    """
    folded, _pairs = fold_integer_or_half(counts, float(center))
    n = int(edge_trim)
    if n > 0 and folded.size > 2 * n + 2:
        folded = folded[n:-n]
    norm = float(np.percentile(folded, 90)) if folded.size else 1.0
    norm = norm or 1.0
    sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
    y = folded / norm
    return folded, sigma, y, norm


def velocity_axis(counts_size: int, vmax: float, n_points: int,
                  edge_trim: int = EDGE_TRIM_DEFAULT,
                  trim_edges: bool = True) -> np.ndarray:
    """Construye el eje de velocidad ``-vmax..vmax`` recortando bordes igual que el folding.

    Se crea el eje completo ``linspace(-vmax, vmax, counts_size // 2)`` y se
    recortan las mismas posiciones ``[edge_trim:-edge_trim]`` que en los datos,
    de modo que no se estira la escala (lo que sesgaría el BHF).
    """
    full_n = int(counts_size) // 2
    velocity = np.linspace(-float(vmax), float(vmax), full_n)
    n = int(edge_trim) if trim_edges else 0
    if n > 0 and velocity.size > 2 * n + 2 and n_points == velocity.size - 2 * n:
        velocity = velocity[n:-n]
    elif velocity.size != n_points:
        velocity = np.linspace(-float(vmax), float(vmax), n_points)
    return velocity
