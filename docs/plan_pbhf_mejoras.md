# Plan: mejoras en P(BHF) — correlación δ(H)/ΔEQ(H) · VBF multi-gaussiano · MaxEnt

> **Nota de mantenimiento (léela antes de seguir los números de línea).**
> Este brief se escribió justo tras el merge del perfil Voigt. Los números de
> línea son **indicativos y ya han derivado** con cambios posteriores; guíate por
> los **nombres de función**, no por las líneas. Correcciones conocidas a fecha de
> guardado (árbol de trabajo v4.11.4, parte aún sin commitear):
> - El gestor de contexto **`line_profile`** ya **no** vive en
>   `mossbauer_distribution.py`; se centralizó en **`core/physics.py`** y se
>   **reexporta** en `mossbauer_distribution.py` (`from core.physics import
>   line_profile, …`), así que `with line_profile(profile, voigt_sigma):` sigue
>   funcionando dentro de `mossbauer_distribution.py` sin cambios.
> - Anclas reales actuales (aprox.): `build_bhf_kernel` ~326,
>   `build_hyperfine_distribution_kernel` ~691, `second_difference_matrix` ~727,
>   `first_difference_matrix` ~740, `fit_hyperfine_distribution` ~1071,
>   `fit_gaussian_hyperfine_distribution` ~1309, `scan_alpha` ~1630.

---

## Contexto y reglas del juego
- Todo el trabajo va en **`mossbauer_distribution.py`** (núcleo puro, sin Qt) + cableado fino en **`gui/distribution_fit.py`** y **`gui/state.py`**. La física NO vive en la GUI.
- **Retrocompatibilidad obligatoria**: cada parámetro nuevo debe tener default que reproduzca el comportamiento actual (pendientes = 0, `reg_mode` sin cambios, formas nuevas opt-in). El golden test `tests/test_headless_golden.py` es del motor **discreto** (no distribución), pero corre la suite entera igualmente:
  `pip install pytest && python -m pytest tests/test_distribution_2d.py tests/test_core_physics.py tests/test_fit_engine.py tests/test_headless_golden.py -q` (desinstala `pytest-qt` o usa `-p no:pytestqt`; falta libEGL headless).
- Pieza clave a reutilizar: en `gui/distribution_fit.py` **ya existe un lazo no lineal externo** (`run_fit` + `outer_specs`, ~líneas 240-423) que refina δ/quad/γ globales envolviendo el solver lineal. Los parámetros no lineales nuevos se enganchan ahí, no reinventes el lazo.

---

## Hueco 1 — Correlación δ(H) y ΔEQ(H)

**Problema actual:** en `build_bhf_kernel` (`mossbauer_distribution.py:352`) y `build_hyperfine_distribution_kernel` (`:717`), **todos** los sextetes de la malla comparten el mismo `delta` y `quad` fijos. Físicamente, en óxidos/aleaciones el desplazamiento isomérico y el desdoblamiento cuadrupolar **correlacionan con H** (Le Caër–Dubois 1979, Wivel–Mørup 1981).

**Modelo a introducir** (correlación lineal, lo estándar):
```
δ_j   = δ0 + κ_δ · (H_j − H_ref)
ΔEQ_j = q0 + κ_q · (H_j − H_ref)
```
con `H_ref` un pivote (usa la media de la malla o `BHF_DEFAULT_T=33`), `κ_δ` en mm/s·T⁻¹, `κ_q` en mm/s·T⁻¹.

**Clave de diseño:** el modelo **sigue siendo lineal en los pesos P_j** — solo cambia cómo se construye cada columna del kernel. El solver `lsq_linear` no se toca.

**Pasos:**
1. En `build_bhf_kernel` / `build_hyperfine_distribution_kernel`: añade `delta_slope=0.0`, `quad_slope=0.0`, `h_ref: float | None = None`. Dentro del bucle de columnas, en vez de `delta=delta, quad=quad` calcula por columna:
   `delta_j = delta + delta_slope*(H_j - h_ref)`, `quad_j = quad + quad_slope*(H_j - h_ref)` (con `h_ref = mean(centers)` si viene `None`).
2. Propaga `delta_slope`/`quad_slope`/`h_ref` por `fit_hyperfine_distribution` (`:1097`). Para `variable="quad"` la correlación análoga es sobre ΔEQ; deja los slopes actuando sobre `delta` (δ(ΔEQ)) y documenta el caso.
3. **Dos niveles de uso:**
   - **(a) Fijos** (mínimo, mantiene solve lineal): el usuario introduce κ_δ, κ_q conocidos del material. Es lo que hace Wivel–Mørup con correlación conocida.
   - **(b) Refinados** (completo): añade `dist_delta_slope` y `dist_quad_slope` a `outer_specs` en `gui/distribution_fit.py:run_fit` para que el `least_squares` externo los ajuste mientras el solve interno resuelve P. **κ son no lineales**, por eso van en la capa externa, nunca en `lsq_linear`.
4. **Riesgo/degeneración:** `κ_δ` y un desplazamiento global de la malla son casi degenerados; acota `κ_δ` a un rango físico (p.ej. |κ_δ| ≤ 0.02 mm/s·T⁻¹) y refina de a poco. Documenta que activar (b) puede robarle anchura a P.
5. **Tests:** verifica que con `delta_slope≠0` el centroide de cada columna se desplaza lo esperado, y que `delta_slope=0` reproduce el kernel actual (allclose).

Coste estimado: **bajo-medio**. Es el de mayor valor físico.

---

## Hueco 2 — VBF multi-gaussiano (Rancourt–Ping 1991)

**Punto de partida:** `fit_gaussian_hyperfine_distribution` (`:1335`) ya es un VBF de **una** gaussiana: parametriza `P = amp·G(μ,σ)`, discretiza en la malla y hace `model = baseline + slope·v − K @ w` con `least_squares` no lineal (`:1348`). VBF completo = **N gaussianas sobre kernel Voigt** (que ya tienes tras el merge). Es literalmente la generalización.

**Nueva función** `fit_vbf_hyperfine_distribution(v, y, *, n_components=2, profile="Voigt", voigt_sigma=..., variable, delta, quad, bhf, gamma, pmin, pmax, nbins, baseline, slope, sharp_components, delta_slope=0.0, quad_slope=0.0, ...) -> BhfDistributionFit`:

1. Construye el kernel **una sola vez** con `build_hyperfine_distribution_kernel` dentro de `with line_profile(profile, voigt_sigma):` (usa el gestor que ya añadimos, `:37`). Reutiliza la correlación δ(H) del Hueco 1 aquí también.
2. Vector de parámetros: `x = [baseline, slope, {A_k, μ_k, log σ_k}_{k=1..N}, {amps nítidos}]`.
3. Residuo:
   ```
   w = Σ_k A_k · gauss_weights(μ_k, σ_k)      # gauss_weights ya existe, :1372
   r = baseline + slope·v − K @ w − fixed_sharp_abs − K_sharp@amps − y
   ```
4. Resuelve con `least_squares` (bounds: `A_k ≥ 0`, `μ_k ∈ [pmin,pmax]`, `σ_k > 0`). x0: reparte `μ_k` uniformemente en `[pmin,pmax]`, `σ_k ≈ rango/(3N)`, `A_k` igual.
5. Devuelve `P = Σ_k A_k G(μ_k,σ_k)` en la malla + `probability` normalizada, y **guarda μ_k, σ_k, A_k** (los parámetros físicos con significado — esa es la ventaja de VBF sobre H-R).
6. **GUI:** añade la forma `"VBF"` al selector `shape` en `gui/distribution_fit.py:run_fit` (junto a Histograma/Gaussiana/Binomial/Fija, `:267-283`) y un spin de nº de componentes en el panel de distribución + `DistributionViewState` (`gui/state.py`).
7. **Riesgo:** *label switching* (permutación de componentes) — ordénalas por μ al devolver. Con N grande hay sobreajuste; empieza con N=2-3.

Coste estimado: **medio**. Alta sinergia con el Voigt ya mergeado.

---

## MaxEnt — regularizador de máxima entropía

**Objetivo:** un tercer `reg_mode = "maxent"` en `fit_hyperfine_distribution` junto a `"tikhonov"`/`"tv"` (selección actual en `:1187-1191`). En vez de penalizar curvatura (`second_difference_matrix`, `:753`) o saltos (`first_difference_matrix`, `:766`), maximiza la entropía → la P **menos comprometida** compatible con los datos, con positividad natural y sin oscilaciones espurias.

**Matemática:**
```
minimiza  Φ(z) = ½ ‖(y − X z)/σ‖²  −  α · S(P)
S(P) = − Σ_j P_j · log(P_j / m_j)        (m_j = modelo por defecto, plano)
sujeto a P_j ≥ 0  (y baseline/slope/nítidos ≥ sus cotas)
```

**Implementación (rama separada, NO IRLS lineal):**
1. La entropía es no cuadrática ⇒ `lsq_linear` no vale. Usa `scipy.optimize.minimize` con `method="L-BFGS-B"` (soporta bounds) sobre `z = [baseline, slope, P (≥0), sharp (≥0)]`, reutilizando la misma `X` (columnas ya montadas en `:1194` aprox.).
2. Da **gradiente analítico** (barato y estabiliza): `∇_P Φ = −Xᵀ W (y − Xz) + α·(log(P/m) + 1)`; para baseline/slope/sharp solo el término de datos.
3. `m_j`: uniforme (entropía relativa a plano). Cuida `P_j→0` con `log` (usa `P_j + ε` o el término `p·log p → 0`).
4. `α`: reutiliza `scan_alpha`/L-curve ya existentes.
5. **Salidas:** rellena el mismo `BhfDistributionFit`. `effective_dof` y `weight_sigma` provienen de un Hessiano distinto (el de MaxEnt: `Hess = XᵀWX + α·diag(1/P_j)`); si te complica, calcula `eff_dof` con ese Hessiano y deja `weight_sigma=None` como fallback (ya hay try/except en `:1307-1312`).
6. **Riesgo:** MaxEnt es sensible a α y a la escala de σ; valida con L-curve. El óptimo es convexo, así que el mínimo es único.

Coste estimado: **medio**. Cambio localizado (una rama nueva en el mismo flujo).

---

## Orden recomendado y verificación
1. **Hueco 1 (correlación δ(H))** primero — reutiliza el solve lineal y el lazo externo existente; compone con los otros dos.
2. **MaxEnt** — rama aislada, no interfiere con 1.
3. **VBF multi-gaussiano** — función nueva + forma GUI; se apoya en el Voigt y (opcionalmente) en la correlación del Hueco 1.

**Tests nuevos** (en `tests/test_distribution_2d.py` o uno nuevo `tests/test_distribution_advanced.py`):
- Correlación: centroides desplazados según κ; κ=0 ≡ kernel actual.
- VBF: recupera una P sintética de 2 gaussianas (μ, σ, A dentro de tolerancia).
- MaxEnt: recupera una P suave sin oscilaciones, ∫P=1, P≥0; comparar rugosidad vs Tikhonov.

**Docs:** entrada en `CHANGELOG.md` ("No publicado") y una línea en `CLAUDE.md` (sección "Modos de ajuste") describiendo los tres.

**Referencias:** Hesse & Rübartsch 1974 (*J. Phys. E*); Le Caër & Dubois 1979; Wivel & Mørup 1981; Rancourt & Ping 1991 (*NIM B* 58, VBF/RECOIL); métodos MaxEnt en Mössbauer (Dou, Le Caër).
