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


#: Canales de borde recortados del espectro DOBLADO.
#:
#: 0 = se conservan todos, como hace NORMOS. El recorte fijo de 1 canal por
#: lado tiraba dos puntos buenos de cada espectro: el primero del array doblado
#: promedia los canales adyacentes al vértice (los más fiables) y solo el
#: último toca los canales extremos. En su lugar, :func:`fold_and_normalize`
#: recorta de forma ADAPTATIVA los extremos que sean outliers de verdad (canal
#: muerto), así que la salvaguarda sigue estando sin coste en datos sanos.
EDGE_TRIM_DEFAULT = 0

#: Canales excluidos de los PARES al buscar el folding point (y al construir la
#: spline de la búsqueda). Esto sí se mantiene: un canal de borde anómalo entra
#: solo en parte de los candidatos y desplazaba el centro detectado ±2 canales.
CENTER_SEARCH_EDGE_GUARD = 1

#: Umbral (en σ de Poisson) para considerar que un punto doblado del borde es un
#: canal muerto y recortarlo. Generoso a propósito: solo dispara con fallos
#: reales de adquisición, no con ruido.
EDGE_OUTLIER_SIGMAS = 8.0

#: Orden de la interpolación subcanal del doblado (1 = lineal, 3 = cúbica).
#:
#: Cuando el punto de doblado NO cae en un canal semientero, cada punto doblado
#: promedia dos muestras que hay que evaluar entre canales. La interpolación
#: LINEAL es un filtro paso bajo que ensancha las líneas: sobre un sexteto
#: sintético con Γ=0.28 mm/s y 512 canales, el Γ ajustado sale hasta un
#: **9.5 % alto** (centro entero, la fracción peor). La CÚBICA reduce ese sesgo
#: a un 2.8 % y también mejora el centro detectado (de ±0.013 canales a
#: ±0.004). Con centro semientero —el caso habitual, y el de todo el banco de
#: validación— no se interpola nada y las dos son idénticas.
#:
#: NORMOS evita el problema por otra vía: trunca el punto de doblado a entero y
#: suma pares de canales enteros, sin interpolar nunca (``normospr.for``,
#: doblado de Hoersten 14.4.89). A cambio, desalinea el par hasta medio canal,
#: que ensancha lo mismo que la interpolación lineal.
FOLD_INTERP_ORDER_DEFAULT = 3


def _channel_sampler(counts: np.ndarray, order: int | None = None,
                     edge_trim: int = 0):
    """Muestreador con caché de una entrada (ver :func:`_build_channel_sampler`).

    El ajuste con ``fit_center`` re-dobla las MISMAS cuentas en cada iteración
    cambiando solo el centro, así que reconstruir la spline cada vez (~100 µs)
    dominaba el coste. La clave es el contenido del array (``tobytes`` sobre
    4 KB cuesta 0.1 µs), no su identidad: así un array reasignado o mutado no
    devuelve una spline obsoleta.
    """
    order = FOLD_INTERP_ORDER_DEFAULT if order is None else int(order)
    key = (counts.tobytes(), counts.shape, order, int(edge_trim))
    cached = _SAMPLER_CACHE.get("key")
    if cached is not None and cached == key:
        return _SAMPLER_CACHE["sampler"]
    sampler = _build_channel_sampler(counts, order, edge_trim)
    _SAMPLER_CACHE["key"] = key
    _SAMPLER_CACHE["sampler"] = sampler
    return sampler


_SAMPLER_CACHE: dict = {"key": None, "sampler": None}


def _build_channel_sampler(counts: np.ndarray, order: int | None = None,
                           edge_trim: int = 0):
    """Devuelve un callable vectorizado ``C(canal)`` con canales 1..N.

    Interpola con una B-spline de grado ``order`` y fuera del rango soportado
    extrapola LINEALMENTE desde el extremo (una spline extrapolada oscila y en
    los bordes solo hay línea base, así que la recta es más segura). Con
    ``order=1``, o con muy pocos canales, es la interpolación lineal histórica.

    ``edge_trim`` excluye ese número de canales de cada extremo al CONSTRUIR la
    spline. Hace falta porque una B-spline interpolante es global: un canal de
    borde muerto —el canal 1 a cero, habitual en ADT reales— se propaga hacia
    el interior con peso ~0.27 por canal y desplazaba el centro detectado
    0.056 canales, aunque el χ² de simetría ya excluyera ese canal de los
    pares. Con la interpolación lineal no pasaba porque su soporte es local.
    """
    c = np.asarray(counts, dtype=float)
    n = c.size
    k = FOLD_INTERP_ORDER_DEFAULT if order is None else int(order)
    t = max(0, int(edge_trim))
    # Recortar solo si queda muestra de sobra para la spline.
    if 2 * t + k + 1 > n:
        t = 0
    x = np.arange(1 + t, n + 1 - t, dtype=float)
    cv = c[t:n - t] if t else c

    if k <= 1 or cv.size < k + 1:
        def sample_inner(ch: np.ndarray) -> np.ndarray:
            return np.interp(np.asarray(ch, dtype=float), x, cv)
    else:
        from scipy.interpolate import make_interp_spline
        spline = make_interp_spline(x, cv, k=k)

        def sample_inner(ch: np.ndarray) -> np.ndarray:
            return spline(np.clip(np.asarray(ch, dtype=float), x[0], x[-1]))

    lo_ch, hi_ch = float(x[0]), float(x[-1])
    slope_lo = float(cv[1] - cv[0]) if cv.size > 1 else 0.0
    slope_hi = float(cv[-1] - cv[-2]) if cv.size > 1 else 0.0

    def sample(ch) -> np.ndarray:
        chan = np.asarray(ch, dtype=float)
        out = sample_inner(chan)
        lo = chan < lo_ch
        hi = chan > hi_ch
        if np.any(lo):
            out = np.where(lo, cv[0] + (chan - lo_ch) * slope_lo, out)
        if np.any(hi):
            out = np.where(hi, cv[-1] + (chan - hi_ch) * slope_hi, out)
        return out

    return sample


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


def fold_integer_or_half(
    counts: np.ndarray, center: float,
    order: int | None = None,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Dobla a N/2 puntos al estilo Normos.

    Canales numerados 1..N. El resultado va de velocidad negativa a positiva,
    desde el par exterior izquierdo hacia el centro y de nuevo hacia el exterior
    derecho. Para centros semienteros ordinarios coincide con el promedio de
    pares simétricos; entre canales interpola con ``order`` (ver
    :data:`FOLD_INTERP_ORDER_DEFAULT`) y en los bordes extrapola linealmente.
    """
    n = counts.size
    n_out = n // 2
    distance = np.arange(n_out, dtype=float) + 0.5
    left_ch = float(center) - distance
    right_ch = float(center) + distance
    sample = _channel_sampler(counts, order)
    folded = 0.5 * (sample(left_ch) + sample(right_ch))
    # np.rint redondea a par en los .5 exactos; el histórico usaba round() de
    # Python, que hace lo mismo, así que los pares no cambian.
    pairs = list(zip(np.rint(left_ch).astype(int).tolist(),
                     np.rint(right_ch).astype(int).tolist()))
    return np.asarray(folded, dtype=float), pairs


def chi2_for_center(counts: np.ndarray, center: float,
                    order: int | None = None) -> tuple[float, int]:
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
    return _chi2_for_center(
        counts, center, _channel_sampler(counts, order, CENTER_SEARCH_EDGE_GUARD))


def _chi2_for_center(counts: np.ndarray, center: float, sample) -> tuple[float, int]:
    """Núcleo de :func:`chi2_for_center` con el muestreador ya construido.

    Se separa para que el barrido de candidatos construya la spline UNA vez en
    vez de una por candidato (la spline es del espectro, no del centro).
    """
    n = counts.size
    lo_ch = 1.0 + CENTER_SEARCH_EDGE_GUARD
    hi_ch = float(n - CENTER_SEARCH_EDGE_GUARD)
    distance = np.arange(n // 2, dtype=float) + 0.5
    left = float(center) - distance
    right = float(center) + distance
    ok = (left >= lo_ch) & (right <= hi_ch)
    if not np.any(ok):
        return 0.0, 0
    d = sample(left[ok]) - sample(right[ok])
    return float(np.sum(d * d)), int(np.count_nonzero(ok))


def geometry_effect_amplitude(counts: np.ndarray, center: float,
                              half_cycle: float | None = None) -> float:
    """Amplitud del **efecto geométrico** del espectro, en cuentas.

    Portado de ``normospr.for`` (bloque ``DO 50``/``DO 300``). Al moverse el
    transductor cambia la distancia fuente-absorbente-detector, lo que modula
    la tasa de cuentas con la POSICIÓN del transductor y no con su velocidad.
    NORMOS lo modela como una sinusoide de medio ciclo, antisimétrica respecto
    al punto de doblado::

        Y(i) = S(i) + A · sin(π (i − c) / PHALF)

    con ``S`` simétrico. La parte antisimétrica se obtiene de las diferencias
    espejo ``D(i) = Y(i) − Y(2c − i) = 2A·sin(...)`` y ``A`` sale por mínimos
    cuadrados. Devuelve 0 si no hay pares utilizables.

    Es un DIAGNÓSTICO, no una corrección del ajuste: al doblar, la parte
    antisimétrica se cancela exactamente. Se mide porque una amplitud alta
    delata un problema de geometría del espectrómetro; NORMOS también la
    imprime en su ``.RES``.
    """
    c = np.asarray(counts, dtype=float)
    n = c.size
    if n < 4:
        return 0.0
    phalf = float(half_cycle) if half_cycle else 0.5 * n
    if phalf <= 0:
        return 0.0
    sample = _channel_sampler(c, None, CENTER_SEARCH_EDGE_GUARD)
    lo_ch = 1.0 + CENTER_SEARCH_EDGE_GUARD
    hi_ch = float(n - CENTER_SEARCH_EDGE_GUARD)
    distance = np.arange(n // 2, dtype=float) + 0.5
    left = float(center) - distance
    right = float(center) + distance
    ok = (left >= lo_ch) & (right <= hi_ch)
    if not np.any(ok):
        return 0.0
    # D en el canal DERECHO del par; el izquierdo es su espejo.
    d = sample(right[ok]) - sample(left[ok])
    basis = np.sin(np.pi * (right[ok] - float(center)) / phalf)
    denom = 2.0 * float(np.sum(basis * basis))
    if denom <= 0.0:
        return 0.0
    return float(np.sum(d * basis) / denom)


def remove_geometry_effect(counts: np.ndarray, center: float,
                           half_cycle: float | None = None
                           ) -> tuple[np.ndarray, float]:
    """Resta el efecto geométrico y devuelve ``(cuentas_corregidas, amplitud)``."""
    amp = geometry_effect_amplitude(counts, center, half_cycle)
    if amp == 0.0:
        return np.asarray(counts, dtype=float), 0.0
    n = np.asarray(counts).size
    phalf = float(half_cycle) if half_cycle else 0.5 * n
    i = np.arange(1, n + 1, dtype=float)
    return np.asarray(counts, dtype=float) - amp * np.sin(np.pi * (i - float(center)) / phalf), amp


#: Ciclos de la búsqueda del folding point (NORMOS hace 2: busca, recalcula el
#: efecto geométrico con el centro nuevo y vuelve a buscar en una ventana
#: estrecha alrededor de él).
CENTER_SEARCH_CYCLES = 2

#: Semianchura (canales) de la ventana del segundo ciclo. NORMOS usa MS=25
#: candidatos de medio canal, o sea ±6.
CENTER_REFINE_HALF_WINDOW = 6.0


def find_best_integer_or_half_center(counts: np.ndarray, cmin: float | None = None,
                                     cmax: float | None = None,
                                     order: int | None = None,
                                     cycles: int = CENTER_SEARCH_CYCLES) -> float:
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
    work = np.asarray(counts, dtype=float)
    best = 0.5 * counts.size
    for cycle in range(max(1, int(cycles))):
        found = _scan_center(work, cmin, cmax, order)
        if found is None:
            return best
        best = found
        if cycle + 1 >= max(1, int(cycles)):
            break
        # Ciclo siguiente (como NORMOS): se resta el efecto geométrico estimado
        # con el centro recién hallado y se reduce la ventana a su entorno.
        work, _amp = remove_geometry_effect(work, best)
        cmin = max(1.5, best - CENTER_REFINE_HALF_WINDOW)
        cmax = min(counts.size - 0.5, best + CENTER_REFINE_HALF_WINDOW)
        if cmax - cmin < 1.0:
            break
    return best


def _scan_center(counts: np.ndarray, cmin: float, cmax: float,
                 order: int | None) -> float | None:
    """Un ciclo de barrido: malla de medio canal + parábola de 3 puntos."""
    candidates = np.arange(cmin, cmax + 1e-9, 0.5)
    sample = _channel_sampler(counts, order, CENTER_SEARCH_EDGE_GUARD)
    values: list[tuple[float, float]] = []
    for center in candidates:
        chi2, n_pairs = _chi2_for_center(counts, float(center), sample)
        if n_pairs:
            values.append((float(center), chi2 / n_pairs))
    if not values:
        return None
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
                       edge_trim: int = EDGE_TRIM_DEFAULT,
                       order: int | None = None,
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Dobla, recorta los bordes y normaliza el espectro.

    Devuelve ``(folded, sigma, y, norm)`` con la línea base normalizada a ~1 y
    ``sigma`` el ruido Poisson normalizado. ``order`` es la interpolación
    subcanal (ver :data:`FOLD_INTERP_ORDER_DEFAULT`).

    ``edge_trim`` es un MÍNIMO forzado de canales a recortar por lado. Por
    defecto es 0 —se conservan todos, como NORMOS— y el recorte lo decide
    :func:`edge_outlier_trim` mirando los datos: solo se van los extremos que
    sean canales muertos de verdad. El recorte es simétrico para que el eje de
    velocidad siga deduciéndose del número de puntos sin estirar la escala.
    """
    folded, _pairs = fold_integer_or_half(counts, float(center), order)
    n = max(int(edge_trim), edge_outlier_trim(folded))
    if n > 0 and folded.size > 2 * n + 2:
        folded = folded[n:-n]
    norm = float(np.percentile(folded, 90)) if folded.size else 1.0
    norm = norm or 1.0
    sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
    y = folded / norm
    return folded, sigma, y, norm


def edge_outlier_trim(folded: np.ndarray,
                      max_trim: int = 3,
                      rel_threshold: float = 0.2) -> int:
    """Cuántos puntos hay que recortar de CADA extremo del espectro doblado.

    Devuelve 0 con datos sanos. Solo dispara con canales muertos: un punto del
    borde cuenta como tal si cae más de ``rel_threshold`` (20 % por defecto)
    por debajo de la mediana de sus vecinos. Un canal a cero deja el punto
    doblado a la mitad de la base (−50 %), muy por encima del umbral, mientras
    que una línea de absorción real en el extremo del rango de velocidad rara
    vez llega al 20 %.

    El recorte es simétrico (se aplica el mayor de los dos lados) para no
    romper la correspondencia con el eje de velocidad.
    """
    f = np.asarray(folded, dtype=float)
    if f.size < 12:
        return 0
    limit = min(int(max_trim), (f.size - 8) // 2)
    trim = 0
    for _ in range(max(0, limit)):
        rest = f[trim:f.size - trim]
        if rest.size < 10:
            break
        ref = float(np.median(rest[2:10])), float(np.median(rest[-10:-2]))
        lo_bad = ref[0] > 0 and (ref[0] - rest[0]) / ref[0] > rel_threshold
        hi_bad = ref[1] > 0 and (ref[1] - rest[-1]) / ref[1] > rel_threshold
        if not (lo_bad or hi_bad):
            break
        trim += 1
    return trim


def velocity_axis(counts_size: int, vmax: float, n_points: int,
                  edge_trim: int | None = None,
                  trim_edges: bool = True) -> np.ndarray:
    """Construye el eje de velocidad ``-vmax..vmax`` recortando bordes igual que el folding.

    Se crea el eje completo ``linspace(-vmax, vmax, counts_size // 2)`` y se
    recortan las mismas posiciones que en los datos, de modo que NO se estira
    la escala (lo que sesgaría el BHF).

    Con ``edge_trim=None`` (por defecto) el recorte se DEDUCE de ``n_points``:
    así funciona igual con el recorte adaptativo de :func:`edge_outlier_trim`,
    que depende de los datos y no de una constante.
    """
    full_n = int(counts_size) // 2
    velocity = np.linspace(-float(vmax), float(vmax), full_n)
    if not trim_edges:
        n = 0
    elif edge_trim is None:
        missing = full_n - int(n_points)
        n = missing // 2 if missing >= 0 and missing % 2 == 0 else -1
    else:
        n = int(edge_trim)
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
