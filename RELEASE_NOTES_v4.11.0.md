# Notas de versión — Fitbauer v4.11.0

## Suite de validación sintética del motor de ajuste (6 niveles)

Esta versión añade `tests/test_synthetic_validation.py`: **34 tests sistemáticos**
que validan el motor de ajuste Mössbauer desde la autoconsistencia matemática hasta
la calibración estadística de incertidumbres con datos Monte Carlo.

---

### Por qué es importante

Hasta ahora los tests usaban datos experimentales (α-Fe, hematita) con tolerancias
relativamente laxas. Esta suite añade una capa anterior, más fundamental:

1. **¿El modelo matemático y el ajustador son autocongruentes?**
   Si se genera un espectro sin ruido con parámetros conocidos y se ajusta, el
   ajustador debe recuperar exactamente esos parámetros (χ²_red < 10⁻⁶).

2. **¿Las derivadas son correctas?**
   Un jacobiano incorrecto provoca convergencia lenta, mínimos falsos o errores de
   covarianza incorrectos — y es difícil detectarlo sin tests explícitos.

3. **¿Las barras de error están bien calibradas?**
   El test de *pull statistics* es el único método riguroso para detectar si el
   programa subestima o sobreestima las incertidumbres reportadas.

---

### Resumen de tests añadidos

| Nivel | Tipo | Tests | Tiempo |
|-------|------|-------|--------|
| 1 — Autoconsistencia | rápidos | 4 | < 1 s |
| 2 — Jacobiano | rápidos | 5 | < 1 s |
| 3 — Monte Carlo | **slow** | 3 | ~46 s |
| 4 — Casos difíciles | rápidos | 8 | < 1 s |
| 5 — Restricciones físicas | rápidos | 9 | < 1 s |
| 6 — Datos reales α-Fe | rápidos | 4 | ~1 s |

---

### Uso en CI

```bash
# CI rápido (excluye Monte Carlo):
pytest -m "not slow"          # 208 tests, ~2 s

# Suite completa (incluyendo Monte Carlo):
pytest                         # 211 tests, ~48 s
```

---

### Resultados numéricos de referencia

Con los datos incluidos en `data_sample/`:

- **α-Fe**: BHF = 33.0 ± 0.5 T, δ = −0.109 ± 0.05 mm/s, Γ ∈ [0.15, 0.50] mm/s
- **Monte Carlo** (200 réplicas, 8 000 cuentas/canal):
  - Sesgo: |media(pull)| estadísticamente compatible con 0
  - Calibración: std(pull) ∈ (0.5, 2.0) para todos los parámetros libres
  - Cobertura 1σ: 48–88 % (teórico 68 %)
- **Autoconsistencia sextete**: χ²_red < 10⁻⁶ tras perturbación 5–10 % en valores iniciales
- **Absorbente grueso**: sat_scale recuperado con error < 20 %

---

### Notas técnicas

- El **generador de referencia** (`ref_sextet`, `ref_doublet`, etc.) es una
  implementación completamente independiente de `core.physics`, basada en matemáticas
  puras. Cualquier diferencia entre generador y ajustador en ausencia de ruido indica
  un bug en el modelo.
- Las **semillas del Monte Carlo** se guardan en `SEEDS_MC` dentro del módulo de test
  para reproducir cualquier réplica fallida.
- El marcador `@pytest.mark.slow` está registrado en `pytest.ini`.
