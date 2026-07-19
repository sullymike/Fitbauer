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
        # Separar por tabulador/;/espacios; una coma dentro de un campo sin
        # punto es decimal de locale europeo (es_ES) y se convierte a punto.
        # Si así no salen ≥2 campos, la coma actúa de separador de columnas.
        parts = [p.strip(",") for p in re.split(r"[;\t\s]+", stripped) if p.strip(",")]
        if len(parts) >= 2:
            parts = [p.replace(",", ".") if ("," in p and "." not in p) else p for p in parts]
        else:
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
    if m:
        source = m.group(1)
    else:
        m_open = re.search(r"<data[^>]*>", text, re.I)
        if m_open:
            # WS5 truncado (descarga parcial, sin </data>): usar lo que sigue
            # al bloque abierto en vez de tragar números de la cabecera XML.
            source = text[m_open.end():]
        elif re.search(r"<\?xml|<ws5|<spectrum", text, re.I):
            raise ValueError(f"Fichero WS5 sin bloque <data> legible: {path}")
        else:
            source = text
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
    # Solo cuentan las líneas puramente numéricas: la línea 2 es el título del
    # espectro y puede contener dígitos ("Fe3O4", "T=300K", "Fc211025") que
    # antes se colaban como velocidades y disparaban vmax.
    nums: list[float] = []
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        try:
            vals = [float(t.replace("D", "E").replace("d", "e")) for t in tokens]
        except ValueError:
            continue
        nums.extend(vals)
    # Cabecera residual de un solo número (p. ej. "2" de "2d") antes de los
    # bloques de 256.
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


#: Canales de borde recortados tras el folding (y excluidos del chi² de centro).
EDGE_TRIM_DEFAULT = 1


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
    """Chi² de simetría por pares para un centro candidato.

    Usa la MISMA interpolación subcanal que el folding (no ``round``, que con
    centros semienteros generaba pares duplicados o autocomparados) y devuelve
    el número de pares realmente evaluados: los que caen fuera de rango se
    saltan y NO deben contar en la normalización, o los candidatos junto al
    borde de la ventana quedan artificialmente favorecidos.

    Los ``EDGE_TRIM_DEFAULT`` canales extremos se excluyen SIEMPRE de la
    comparación, igual que el folding los recorta: un canal de borde anómalo
    (p. ej. canal 1 muerto, habitual en ADT reales) entra solo en parte de los
    candidatos y desplazaba el centro detectado hasta ±2 canales.
    """
    n = counts.size
    lo_ch = 1.0 + EDGE_TRIM_DEFAULT
    hi_ch = float(n - EDGE_TRIM_DEFAULT)
    chi2 = 0.0
    n_valid = 0
    for j in range(n // 2):
        distance = j + 0.5
        left = center - distance
        right = center + distance
        if left < lo_ch or right > hi_ch:
            continue
        d = interp_channel_1based(counts, left) - interp_channel_1based(counts, right)
        chi2 += d * d
        n_valid += 1
    return chi2, n_valid


def find_best_integer_or_half_center(counts: np.ndarray, cmin: float | None = None,
                                     cmax: float | None = None) -> float:
    """Busca el folding point con interpolación subcanal.

    Normos no se queda en canales enteros/semienteros: primero localiza el
    mínimo de chi² en una malla y después interpola el mínimo. Internamente esta
    GUI usa el centro de simetría (≈255.77 para un "upper folding point" Normos
    ≈511.55 en 512 canales), por eso el número Normos es aproximadamente el
    doble del mostrado aquí.

    Sin ``cmin``/``cmax`` la ventana es ``N/2 ± 20`` canales: depende del número
    real de canales (el antiguo default 250.5–262.5 solo valía para 512 y daba
    centros absurdos con 256 o 1024 canales).
    """
    half = 0.5 * counts.size
    if cmin is None:
        cmin = max(1.5, half - 20.0)
    if cmax is None:
        cmax = min(counts.size - 0.5, half + 20.0)
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


# ── Drive senoidal (NORMOS: TRIANG=.FALSE., FOLD=.FALSE., SIMULT=.TRUE.) ───────
# Con drive senoidal la velocidad NO avanza linealmente con el canal, así que no
# se dobla: se asigna a cada canal su velocidad real v_i = vmax·sin(2π(i−c0)/N) y
# se ajusta el espectro sin plegar completo. El eje resultante NO es monótono
# (la misma velocidad aparece en varias fases), lo que el motor de ajuste tolera
# porque evalúa el modelo punto a punto.

SINE_PHASE_QUARTER = 0.25  # el pico del seno está N/4 canales tras el cruce por 0


def sine_velocity_axis(counts_size: int, vmax: float, c0: float) -> np.ndarray:
    """Velocidad real por canal para un drive sinusoidal, sin doblar.

    ``v_i = vmax·sin(2π(i − c0)/N)`` con canales 1-based ``i = 1..N`` y ``c0`` la
    fase (canal de cruce por cero ascendente). Devuelve un eje de tamaño ``N`` no
    monótono.
    """
    n = int(counts_size)
    if n <= 0:
        return np.array([], dtype=float)
    i = np.arange(1, n + 1, dtype=float)
    return float(vmax) * np.sin(2.0 * np.pi * (i - float(c0)) / n)


def symmetry_center_to_c0(center: float, counts_size: int) -> float:
    """Convierte el punto de simetría (extremo del seno) en la fase ``c0``.

    El pico del seno (``v = +vmax``) está en ``i = c0 + N/4``, luego
    ``c0 = center − N/4``.
    """
    return float(center) - SINE_PHASE_QUARTER * int(counts_size)


def normalize_unfolded(counts: np.ndarray
                       ) -> tuple[np.ndarray, np.ndarray, float]:
    """Normaliza el espectro SIN doblar y da ``sigma`` Poisson por canal.

    Paralelo a :func:`fold_and_normalize` pero sin plegado ni factor ``/2`` (no
    hay promedio de canales). Devuelve ``(sigma, y, norm)`` con la línea base a
    ~1.
    """
    c = np.asarray(counts, dtype=float)
    norm = float(np.percentile(c, 90)) if c.size else 1.0
    norm = norm or 1.0
    sigma = np.sqrt(np.maximum(c, 1.0)) / norm
    y = c / norm
    return sigma, y, norm


def find_sine_symmetry_center(counts: np.ndarray) -> float:
    """Localiza el punto de simetría (extremo del seno) del primer cuarto (~N/4).

    El espectro senoidal es simétrico respecto a los extremos del drive (donde
    ``v = ±vmax``). Se busca el del primer cuarto reutilizando el mismo criterio
    de simetría por pares (:func:`chi2_for_center`) que el folding triangular,
    pero en una ventana ancha alrededor de ``N/4``.
    """
    n = int(np.asarray(counts).size)
    if n < 8:
        return SINE_PHASE_QUARTER * n
    lo = max(1.5, 0.15 * n)
    hi = 0.40 * n
    return find_best_integer_or_half_center(counts, lo, hi)
