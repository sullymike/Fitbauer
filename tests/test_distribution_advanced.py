"""Correlación δ(H)/ΔEQ(H), VBF multi-gaussiano y regularización MaxEnt."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mossbauer_distribution as md


def _grid():
    return md.parameter_grid(0.0, 50.0, 40)


# ── Hueco 1: correlación δ(H)/ΔEQ(H) ────────────────────────────────────────
def test_kernel_correlation_slope_zero_reproduces_classic():
    v = np.linspace(-10, 10, 250)
    centers = _grid()
    K0 = md.build_bhf_kernel(v, centers, delta=0.15, quad=0.05)
    Kc = md.build_bhf_kernel(v, centers, delta=0.15, quad=0.05,
                             delta_slope=0.0, quad_slope=0.0)
    assert np.allclose(K0, Kc)


def test_kernel_correlation_shifts_column_centroids():
    v = np.linspace(-10, 10, 400)
    centers = _grid()
    href = float(np.mean(centers))
    K0 = md.build_bhf_kernel(v, centers, delta=0.0)
    Ks = md.build_bhf_kernel(v, centers, delta=0.0, delta_slope=0.02, h_ref=href)
    # El centroide (posición ponderada) de una columna de alto campo se desplaza
    # respecto al campo pivote; la columna en H≈href apenas cambia.
    def centroid(col):
        return float(np.sum(v * col) / np.sum(col))
    j_hi = centers.size - 1
    assert abs(centroid(Ks[:, j_hi]) - centroid(K0[:, j_hi])) > 1e-3
    j_ref = int(np.argmin(np.abs(centers - href)))
    assert abs(centroid(Ks[:, j_ref]) - centroid(K0[:, j_ref])) < 5e-2


def test_fit_hyperfine_distribution_accepts_slopes():
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1e-3,
                                      fit_slope=False, delta_slope=0.003)
    assert r.success and np.all(r.weights >= -1e-9)



def test_correlation_curve_y_banda():
    """δ(x) = δ + κ(x − ref) y σ²(x) = σ²_δ + (x − ref)²σ²_κ + 2(x − ref)cov."""
    x = np.array([0.0, 1.0, 2.0])
    y, s = md.correlation_curve(x, 0.3, 0.1, 1.0)
    np.testing.assert_allclose(y, [0.2, 0.3, 0.4])
    assert np.all(s == 0.0)                          # sin varianzas: sin banda
    y, s = md.correlation_curve(x, 0.3, 0.1, 1.0, var_base=0.04, var_slope=0.01,
                                cov_base_slope=0.01)
    np.testing.assert_allclose(s ** 2, [0.04 + 0.01 - 0.02, 0.04, 0.04 + 0.01 + 0.02])


def test_global_parameter_covariance_coincide_con_mco_lineal():
    """En un modelo lineal la covarianza linealizada es la de mínimos cuadrados."""
    rng = np.random.default_rng(3)
    x = np.linspace(-1, 1, 200)
    y = 0.5 + 2.0 * x + rng.normal(0, 0.1, x.size)
    J = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(J, y, rcond=None)
    r = y - J @ coef
    cov = md.global_parameter_covariance(J, r)
    s2 = float(r @ r) / (x.size - 2)
    np.testing.assert_allclose(cov, s2 * np.linalg.inv(J.T @ J))
    # Los grados de libertad que consume la distribución reducen el denominador.
    cov_dof = md.global_parameter_covariance(J, r, inner_dof=50)
    np.testing.assert_allclose(cov_dof, cov * (x.size - 2) / (x.size - 52))
    assert md.global_parameter_covariance(J[:2], r[:2]) is None   # sin dof


def test_slope_ref_es_la_referencia_del_kernel():
    """El resultado guarda la x en la que δ y ΔEQ valen sus globales."""
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1e-3,
                                      fit_slope=False, delta_slope=0.003)
    assert r.slope_ref == pytest.approx(float(np.mean(r.bhf_centers)))
    assert r.as_dict()["slope_ref"] == r.slope_ref
    rv = md.fit_vbf_hyperfine_distribution(v, y, n_components=1, pmin=0, pmax=50,
                                           nbins=40, delta_slope=0.003)
    assert rv.slope_ref == pytest.approx(float(np.mean(rv.bhf_centers)))

def test_diagnosticos_de_residuos_distinguen_ruido_de_estructura():
    """lag-1 ≈ 0 y |z| de rachas pequeño con ruido blanco; con una onda lenta
    en los residuos lag-1 → 1 y z muy negativo (pocas rachas)."""
    rng = np.random.default_rng(3)
    blanco = rng.standard_normal(512)
    assert abs(md.residual_lag1(blanco)) < 0.15
    assert abs(md.residual_runs_z(blanco)) < 3.0
    onda = np.sin(np.linspace(0, 6 * np.pi, 512)) + 0.1 * blanco
    assert md.residual_lag1(onda) > 0.8
    assert md.residual_runs_z(onda) < -10.0
    assert np.isnan(md.residual_runs_z(np.ones(10)))


def test_bondad_de_distribucion_chi2_reducido_y_aic_como_el_discreto():
    """Con el modelo correcto y la σ verdadera, χ²_ν ≈ 1; AIC/BIC usan la
    misma definición que el ajuste discreto (N·ln(χ²/N) + 2k, + k·ln N)."""
    v = np.linspace(-10, 10, 400)
    centers = _grid()
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    clean = 1.0 - K @ (P / P.sum() * 2.0)
    sigma = np.full(v.size, 2e-3)
    y = clean + np.random.default_rng(5).normal(0.0, 2e-3, v.size)
    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1.0,
                                      sigma=sigma)
    g = md.distribution_goodness(r.residuals, sigma, r.effective_dof, n_outer=2)
    assert g["n_params"] == pytest.approx(r.effective_dof + 2)
    assert g["dof"] == pytest.approx(v.size - g["n_params"])
    assert 0.8 < g["red_chi2"] < 1.25
    chi2 = float(np.sum((r.residuals / sigma) ** 2))
    n = v.size
    assert g["aic"] == pytest.approx(n * np.log(chi2 / n) + 2 * g["n_params"])
    assert g["bic"] == pytest.approx(n * np.log(chi2 / n) + g["n_params"] * np.log(n))
    # Sin σ: solo RMS y diagnósticos.
    g0 = md.distribution_goodness(r.residuals, None, r.effective_dof)
    assert "chi2" not in g0 and g0["rms"] == pytest.approx(r.rms)


def test_formas_parametricas_guardan_sus_parametros_ajustados():
    """VBF, binomial y fija cuentan sus parámetros ajustados como dof."""
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    rv = md.fit_vbf_hyperfine_distribution(v, y, n_components=2, pmin=0, pmax=50, nbins=40)
    assert rv.effective_dof == 2 + 3 * 2          # fondo + pendiente + (A, μ, σ)×2
    rb = md.fit_binomial_hyperfine_distribution(v, y, pmin=0, pmax=50)
    assert rb.effective_dof is not None and rb.effective_dof >= 3


def test_momentos_de_la_distribucion():
    x = np.linspace(-6, 14, 201)          # malla simétrica en torno a μ
    p = np.exp(-0.5 * ((x - 4.0) / 1.5) ** 2)
    m = md.distribution_moments(x, p)
    assert m["mean"] == pytest.approx(4.0, abs=1e-3)
    assert m["std"] == pytest.approx(1.5, rel=1e-2)
    assert m["mode"] == pytest.approx(4.0)
    assert md.distribution_moments(x, np.zeros_like(x)) == {}

# ── Hueco 2: VBF multi-gaussiano ────────────────────────────────────────────
def test_vbf_recovers_two_gaussians():
    v = np.linspace(-10, 10, 400)
    centers = md.parameter_grid(0.0, 50.0, 80)

    def G(mu, s):
        w = np.exp(-0.5 * ((centers - mu) / s) ** 2)
        return w / np.trapezoid(w, centers)

    P_true = 1.0 * G(20.0, 2.0) + 0.6 * G(45.0, 3.0)
    K = md.build_bhf_kernel(v, centers, delta=0.0, gamma=0.25)
    y = 1.0 - K @ (P_true * 0.5)
    rng = np.random.default_rng(1)
    y = y + rng.normal(0, 8e-4, y.size)

    r = md.fit_vbf_hyperfine_distribution(v, y, n_components=2, profile="Lorentziana",
                                          pmin=0, pmax=50, nbins=80, gamma=0.25)
    assert r.success
    assert r.vbf_components is not None and len(r.vbf_components) == 2
    mus = [c[1] for c in r.vbf_components]
    # ordenadas por μ y cerca de los valores verdaderos
    assert mus == sorted(mus)
    assert abs(mus[0] - 20.0) < 2.0
    assert abs(mus[1] - 45.0) < 3.0


def test_vbf_single_component_matches_gaussian_shape():
    v = np.linspace(-10, 10, 300)
    r = md.fit_vbf_hyperfine_distribution(v, np.ones_like(v), n_components=1,
                                          profile="Lorentziana", pmin=0, pmax=50, nbins=60)
    assert r.success and r.vbf_components is not None and len(r.vbf_components) == 1


def test_gaussiana_shape_is_vbf_single_lorentz():
    """La forma 'Gaussiana' de la GUI es VBF con N=1 y línea Lorentziana: recupera
    una gaussiana de BHF conocida y conserva la etiqueta shape='Gaussiana'."""
    v = np.linspace(-10, 10, 400)
    centers = md.parameter_grid(0.0, 50.0, 80)
    w = np.exp(-0.5 * ((centers - 30.0) / 2.0) ** 2)
    P_true = w / np.trapezoid(w, centers)
    K = md.build_bhf_kernel(v, centers, delta=0.0, gamma=0.25)
    y = 1.0 - K @ (P_true * 0.5)

    r = md.fit_vbf_hyperfine_distribution(
        v, y, n_components=1, profile="Lorentz", shape="Gaussiana",
        pmin=0, pmax=50, nbins=80, gamma=0.25)
    assert r.success
    assert r.shape == "Gaussiana"            # etiqueta conservada para sesión/informe
    assert r.vbf_n_components == 1
    assert r.vbf_components is not None and len(r.vbf_components) == 1
    assert abs(r.vbf_components[0][1] - 30.0) < 1.5   # μ recuperado
    assert abs(r.fitted_dist_center - 30.0) < 1.5



def test_vbf_sigma_bounds_auto_and_explicit():
    """0/None = límites automáticos; una σ máx explícita manda sobre el mínimo
    automático; máx ≤ mín es un error."""
    assert md.vbf_sigma_bounds(1e-3, 50.0) == (1e-3, 50.0)
    assert md.vbf_sigma_bounds(1e-3, 50.0, 0.0, 0.0) == (1e-3, 50.0)
    assert md.vbf_sigma_bounds(1e-3, 50.0, 0.5, 4.0) == (0.5, 4.0)
    assert md.vbf_sigma_bounds(0.25, 50.0, None, 0.2) == (0.1, 0.2)
    with pytest.raises(ValueError):
        md.vbf_sigma_bounds(1e-3, 50.0, 3.0, 2.0)


def test_vbf_sigma_limits_bound_every_component():
    """σ mín/máx son comunes a todas las gaussianas y el resultado las expone."""
    v = np.linspace(-10, 10, 400)
    centers = md.parameter_grid(0.0, 50.0, 80)

    def G(mu, s):
        w = np.exp(-0.5 * ((centers - mu) / s) ** 2)
        return w / np.trapezoid(w, centers)

    # Una gaussiana estrecha (σ=0.6) y otra ancha (σ=6): las cotas [1.5, 3]
    # tienen que ensanchar la primera y estrechar la segunda.
    K = md.build_bhf_kernel(v, centers, delta=0.0, gamma=0.25)
    y = 1.0 - K @ ((G(20.0, 0.6) + 0.8 * G(40.0, 6.0)) * 0.5)
    libre = md.fit_vbf_hyperfine_distribution(v, y, n_components=2, profile="Lorentziana",
                                              pmin=0, pmax=50, nbins=80, gamma=0.25)
    assert libre.vbf_sigma_bounds == (1e-3, 50.0)        # automático
    sig_libre = sorted(c[2] for c in libre.vbf_components)
    assert sig_libre[0] < 1.5 and sig_libre[1] > 3.0

    r = md.fit_vbf_hyperfine_distribution(v, y, n_components=2, profile="Lorentziana",
                                          pmin=0, pmax=50, nbins=80, gamma=0.25,
                                          sigma_min=1.5, sigma_max=3.0)
    assert r.success and r.vbf_sigma_bounds == (1.5, 3.0)
    for _a, _mu, sig in r.vbf_components:
        assert 1.5 - 1e-9 <= sig <= 3.0 + 1e-9
    assert r.as_dict()["vbf_sigma_bounds"] == [1.5, 3.0]



@pytest.mark.parametrize("reg_mode", ["tikhonov", "tv"])
def test_banda_mc_de_p_coincide_con_reajustes(reg_mode):
    """La banda 1σ (band_replicas) es la dispersión real de P al reajustar con
    ruido, respetando P ≥ 0; sin pedirla no se calcula."""
    v = np.linspace(-6, 6, 300)
    centers = md.parameter_grid(0.0, 3.0, 40)
    P = (np.exp(-0.5 * ((centers - 0.8) / 0.12) ** 2)
         + 0.6 * np.exp(-0.5 * ((centers - 1.8) / 0.15) ** 2))
    K = md.build_hyperfine_distribution_kernel(v, centers, variable="quad", bhf=0.0,
                                               delta=0.3, gamma=0.25)
    y0 = 1.0 - K @ (P / P.sum() * 1.5)
    sig = np.full(v.size, 4e-3)
    kw = dict(variable="quad", bhf=0.0, delta=0.3, gamma=0.25, pmin=0.0, pmax=3.0,
              nbins=40, alpha=1.0, sigma=sig, reg_mode=reg_mode, fit_slope=False)
    rng = np.random.default_rng(2)
    y = y0 + rng.normal(0, sig)
    assert md.fit_hyperfine_distribution(v, y, **kw).probability_sigma is None
    r = md.fit_hyperfine_distribution(v, y, band_replicas=80, **kw)
    sp = r.probability_sigma
    assert sp.shape == r.probability.shape and np.all(sp >= 0)
    chi2nu = float(np.sum((r.residuals / sig) ** 2)) / (v.size - r.effective_dof)
    reaj = [md.fit_hyperfine_distribution(
        v, r.fitted_curve + np.sqrt(chi2nu) * rng.normal(0, sig), **kw).probability
        for _ in range(60)]
    mc = np.std(reaj, axis=0, ddof=1)
    pico = r.probability > 0.2 * r.probability.max()
    assert 0.7 < float(np.median(sp[pico] / mc[pico])) < 1.4
    assert len(r.as_dict()["probability_sigma"]) == r.probability.size

# ── MaxEnt ──────────────────────────────────────────────────────────────────
def test_maxent_positive_normalized_and_peaked():
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    rng = np.random.default_rng(0)
    y = y + rng.normal(0, 2e-3, y.size)

    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1e-3,
                                      reg_mode="maxent", fit_slope=False)
    assert r.success
    assert np.all(r.weights >= -1e-9)
    assert abs(float(np.trapezoid(r.probability, r.bhf_centers)) - 1.0) < 1e-6
    peak = float(r.bhf_centers[int(np.argmax(r.weights))])
    assert 28.0 < peak < 38.0
    assert r.effective_dof is not None and r.effective_dof > 0


def test_tabla_de_datos_de_la_distribucion_1d_y_2d(tmp_path):
    """1D: x, P, σ_P (si hay banda), peso y columnas extra; 2D: una fila por
    celda en formato largo, con P(x_i, y_j) en su sitio."""
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1.0,
                                      band_replicas=20)
    extra = {"delta_curve_mm_s": np.zeros(40), "mal": np.zeros(3)}
    cols, rows = md.distribution_data_table(r, extra)
    assert cols == ["BHF_T", "P_normalized", "sigma_P", "weight", "delta_curve_mm_s"]
    assert rows.shape == (40, 5)
    out = tmp_path / "d.dat"
    md.write_distribution_data(out, r, header=["línea 1"])
    texto = out.read_text(encoding="utf-8").splitlines()
    assert texto[0] == "# línea 1" and texto[1] == "BHF_T\tP_normalized\tsigma_P\tweight"

    p2 = np.arange(12, dtype=float).reshape(3, 4)
    r2 = md.BhfQuadDistribution2DFit(
        bhf_centers=np.array([10.0, 20.0, 30.0]), quad_centers=np.array([0.0, 0.1, 0.2, 0.3]),
        weights=p2.ravel(), probability=p2, fitted_curve=np.zeros(1), residuals=np.zeros(1),
        baseline=1.0, slope=0.0, alpha_bhf=1.0, alpha_quad=1.0, rms=0.0, success=True,
        message="", x_variable="bhf", y_variable="quad")
    cols, rows = md.distribution_data_table(r2)
    assert cols == ["BHF_T", "dEQ_mm_s", "P_normalized", "weight"]
    assert rows.shape == (12, 4)
    fila = rows[(rows[:, 0] == 20.0) & (rows[:, 1] == 0.3)][0]
    assert fila[2] == p2[1, 3]


# ── Forma de Czjzek (P(ΔEQ) de sólidos desordenados) ────────────────────────
@pytest.mark.parametrize("delta0", [0.0, 0.8])
def test_czjzek_coincide_con_la_norma_de_un_tensor_aleatorio(delta0):
    """La densidad es la de |u₀ + U| con U gaussiano en 5 dimensiones."""
    sigma = 0.3
    rng = np.random.default_rng(7)
    u0 = np.zeros(5); u0[2] = delta0          # orientación arbitraria: solo cuenta |u₀|
    muestras = np.linalg.norm(u0 + rng.normal(0.0, sigma, (400_000, 5)), axis=1)
    bordes = np.linspace(0.0, 3.0, 61)
    hist, _ = np.histogram(muestras, bins=bordes, density=True)
    centros = 0.5 * (bordes[1:] + bordes[:-1])
    p = md.czjzek_weights(centros, sigma, delta0)
    assert np.max(np.abs(p - hist)) < 0.03 * np.max(hist)


def test_czjzek_puro_moda_en_dos_sigma_y_cero_en_el_origen():
    x = np.linspace(0.0, 3.0, 3001)
    p = md.czjzek_weights(x, 0.25)
    assert x[np.argmax(p)] == pytest.approx(0.5, abs=2e-3)
    assert p[0] == 0.0
    m = md.distribution_moments(x, p)
    assert m["mean"] == pytest.approx(2.128 * 0.25, rel=5e-3)
    assert m["std"] / m["mean"] == pytest.approx(0.323, abs=5e-3)
    # Con ΔEQ₀ ≫ σ tiende a una gaussiana centrada en ΔEQ₀.
    q = md.czjzek_weights(x, 0.05, 1.5)
    mq = md.distribution_moments(x, q)
    assert mq["mean"] == pytest.approx(1.5 + 2 * 0.05 ** 2 / 1.5, abs=5e-3)
    assert mq["std"] == pytest.approx(0.05, rel=0.05)


@pytest.mark.parametrize("extended,delta0", [(False, None), (True, 0.9)])
def test_ajuste_czjzek_recupera_sus_parametros(extended, delta0):
    v = np.linspace(-4, 4, 400)
    centers = md.parameter_grid(0.0, 3.0, 120)
    K = md.build_hyperfine_distribution_kernel(v, centers, variable="quad",
                                               delta=0.35, gamma=0.25)
    sig_true = 0.25 if not extended else 0.2
    P = md.czjzek_weights(centers, sig_true, delta0 or 0.0)
    rng = np.random.default_rng(3)
    ruido = 2e-3
    y = 1.0 - K @ (P * 0.08) + rng.normal(0.0, ruido, v.size)
    r = md.fit_czjzek_hyperfine_distribution(
        v, y, extended=extended, variable="quad", delta=0.35, gamma=0.25,
        pmin=0.0, pmax=3.0, nbins=120, sigma=np.full(v.size, ruido))
    assert r.success and r.shape == ("Czjzek ext." if extended else "Czjzek")
    assert r.czjzek_sigma == pytest.approx(sig_true, abs=4 * r.czjzek_sigma_err + 1e-3)
    assert 0 < r.czjzek_sigma_err < 0.05
    if extended:
        assert r.czjzek_delta0 == pytest.approx(delta0, abs=4 * r.czjzek_delta0_err + 1e-3)
    else:
        assert r.czjzek_delta0 is None
    assert r.effective_dof == 2 + (3 if extended else 2)
    g = md.distribution_goodness(r.residuals, np.full(v.size, ruido), r.effective_dof)
    assert g["red_chi2"] == pytest.approx(1.0, abs=0.25)


# ── Correlaciones de P con los globales ─────────────────────────────────────
def test_covarianza_de_momentos_en_todas_las_formas():
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    rng = np.random.default_rng(1)
    y = 1.0 - K @ (P / P.sum() * 2.0) + rng.normal(0, 2e-3, v.size)
    s = np.full(v.size, 2e-3)
    resultados = [
        md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1e-2,
                                      sigma=s, band_replicas=40),
        md.fit_vbf_hyperfine_distribution(v, y, n_components=1, pmin=0, pmax=50, nbins=40),
        md.fit_binomial_hyperfine_distribution(v, y, pmin=20, pmax=40),
    ]
    for r in resultados:
        assert r.moment_cov is not None and r.moment_cov.shape == (2, 2), r.shape
        assert np.all(np.diag(r.moment_cov) > 0), r.shape
    # Sin réplicas el histograma no la estima.
    assert md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40,
                                         alpha=1e-2).moment_cov is None


def test_correlacion_gamma_anchura_coincide_con_el_ajuste_conjunto():
    """La correlación σ_P–Γ que da la GUI (P reajustada + sensibilidad) es la
    del ajuste conjunto de todos los parámetros a la vez."""
    pytest.importorskip("PySide6")
    from scipy.optimize import least_squares
    from gui.distribution_fit import DistributionFitMixin

    v = np.linspace(-6, 6, 240)
    c = md.parameter_grid(0.0, 3.0, 60)

    def gw(mu, s):
        w = np.exp(-0.5 * ((c - mu) / s) ** 2)
        return w / np.trapezoid(w, c)

    ruido = 1e-3
    K = md.build_hyperfine_distribution_kernel(v, c, variable="quad", delta=0.3, gamma=0.25)
    y = 1.0 - K @ (0.06 * gw(1.0, 0.25)) + np.random.default_rng(2).normal(0, ruido, v.size)

    def conjunto(x):
        b, A, mu, ls, lg = x
        Kg = md.build_hyperfine_distribution_kernel(v, c, variable="quad", delta=0.3,
                                                    gamma=float(np.exp(lg)))
        return (b - Kg @ (A * gw(mu, np.exp(ls))) - y) / ruido

    r = least_squares(conjunto, [1.0, 0.06, 1.0, np.log(0.25), np.log(0.25)])
    C = np.linalg.pinv(r.jac.T @ r.jac)
    r_conjunto = C[3, 4] / np.sqrt(C[3, 3] * C[4, 4])

    def interno(lg):
        return md.fit_vbf_hyperfine_distribution(
            v, y, n_components=1, profile="Lorentz", variable="quad", delta=0.3,
            gamma=float(np.exp(lg)), pmin=0, pmax=3, nbins=60, fit_slope=False)

    o = least_squares(lambda x: interno(x[0]).residuals / ruido, [np.log(0.2)], diff_step=1e-4)
    cov_g = np.linalg.pinv(o.jac.T @ o.jac)
    D = DistributionFitMixin._distribution_moment_sensitivity(
        lambda x: interno(x[0]), o.x, np.array([np.log(0.05)]), np.array([np.log(1.0)]))
    mom = interno(o.x[0]).moment_cov + D @ cov_g @ D.T
    r_gui = (D @ cov_g)[1, 0] / np.sqrt(mom[1, 1] * cov_g[0, 0])
    assert r_conjunto < -0.8
    assert r_gui == pytest.approx(r_conjunto, abs=0.05)


def test_matriz_de_correlacion_desde_parejas_o_completa():
    from core.result_views import correlation_matrix
    pares = [{"param1": "a", "param2": "b", "corr": -0.9},
             {"param1": "b", "param2": "c", "corr": 0.3}]
    labels, m = correlation_matrix({"pairs": pares})
    assert labels == ["a", "b", "c"]
    assert m[0, 1] == m[1, 0] == -0.9 and m[1, 2] == 0.3
    assert np.isnan(m[0, 2]) and np.allclose(np.diag(m), 1.0)
    labels, m = correlation_matrix({"keys": ["x", "y"], "matrix": [[1, 0.5], [0.5, 1]]})
    assert labels == ["x", "y"] and m[0, 1] == 0.5
    assert correlation_matrix({}) is None
    assert correlation_matrix({"pairs": []}) is None


def test_formas_parametricas_ponderan_con_la_sigma_de_los_datos():
    """Gaussiana/VBF, binomial y Fija usan la σ de los datos: canales con σ
    enorme (aquí, corrompidos) no pesan; sin σ, arrastran el ajuste."""
    v = np.linspace(-10, 10, 400)
    centers = _grid()
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    malo = v > 0
    y_mal = y.copy()
    y_mal[malo] += 0.02 * np.sin(3 * v[malo])            # estructura espuria
    sigma = np.where(malo, 1e3, 1e-3)
    con = md.fit_vbf_hyperfine_distribution(v, y_mal, n_components=1, pmin=0, pmax=50,
                                            nbins=40, sigma=sigma)
    sin = md.fit_vbf_hyperfine_distribution(v, y_mal, n_components=1, pmin=0, pmax=50,
                                            nbins=40)
    ref = md.fit_vbf_hyperfine_distribution(v, y, n_components=1, pmin=0, pmax=50, nbins=40)
    mu = lambda r: r.vbf_components[0][1]
    assert abs(mu(con) - mu(ref)) < abs(mu(sin) - mu(ref))
    assert abs(np.mean(con.residuals[~malo])) < abs(np.mean(sin.residuals[~malo])) + 1e-9
    # Fija: el problema lineal ponderado ignora los canales con σ enorme.
    rf_con = md.fit_fixed_hyperfine_distribution(v, y_mal, centers, P, sigma=sigma)
    rf_sin = md.fit_fixed_hyperfine_distribution(v, y_mal, centers, P)
    assert (np.sqrt(np.mean(rf_con.residuals[~malo] ** 2))
            < np.sqrt(np.mean(rf_sin.residuals[~malo] ** 2)))
    # Binomial: acepta la σ y la usa (resultado distinto con datos corrompidos).
    rb_con = md.fit_binomial_hyperfine_distribution(v, y_mal, pmin=20, pmax=40, sigma=sigma)
    rb_sin = md.fit_binomial_hyperfine_distribution(v, y_mal, pmin=20, pmax=40)
    assert rb_con.binomial_start != pytest.approx(rb_sin.binomial_start, abs=1e-6)
