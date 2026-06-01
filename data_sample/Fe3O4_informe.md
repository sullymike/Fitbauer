# Informe de ajuste Mössbauer Fe-57

- **Fecha:** 2026-05-31 02:13:42
- **Programa:** Mössbauer Fe-57 v2IA v2.2
- **Fichero:** Fe3O4.adt
- **Modo:** discrete / componentes discretos
- **Perfil:** Lorentziana
- **Vmax:** 11.966 mm/s
- **Folding point interno:** 257.42647
- **Normalización:** 204561.32

## Calibración asociada

- Calibración asociada sin incertidumbre explícita de Vmax. Considera error sistemático adicional.

```json
{
  "source": "web_api",
  "medida_id": 1352,
  "calibration_id": 1230,
  "calibration_sample": "Fc300425",
  "calibration_date": "2025-04-30T19:04:25.166832+02:00",
  "velocity_calibrated": 11.966,
  "isomer_shift": -0.1084,
  "calibration_file_name": "Fc300425.ws5",
  "calibration_file_path": "/home/jorge/Mossbauer/medidas/Fc300425.ws5"
}
```

## Métricas del ajuste

| Métrica | Valor |
|---|---:|
| RMS | 0.0017439261 |
| χ² | 319.27995 |
| χ² reducido | 1.3415124 |
| Grados de libertad | 238 |
| AIC | 90.098442 |
| BIC | 146.69579 |
| Parámetros | 16 |

**Diagnóstico de residuo**

| Indicador | Valor |
|---|---:|
| Autocorrelación lag-1 | 0.315331 |
| Test de rachas z | -4.40018 |
| Correlación antisimétrica | -0.164214 |

## Correlaciones de parámetros

- Máxima |r| = 0.8589 entre `s1_depth` y `s1_int1`.

## Componentes y áreas

| Componente | Tipo | Área integrada | Porcentaje |
|---:|---|---:|---:|
| 1 | Sextete | 0.064321874 | 32.928% |
| 2 | Sextete | 0.13101723 | 67.072% |

## Parámetros

| Parámetro | Valor | Error 1σ | Fijo |
|---|---:|---:|:---:|
| `baseline` | 1.0002006 | 0.000195185 | no |
| `slope` | 1.0567953e-05 | 1.65357e-05 | no |
| `s1_delta` | 0.54702733 | 0.00923379 | no |
| `s1_quad` | 0.054843523 | 0.0174855 | no |
| `s1_bhf` | 45.757611 | 0.0745005 | no |
| `s1_gamma1` | 0.24651868 | 0.0216861 | no |
| `s1_gamma2` | 0.90708727 | 0.10798 | no |
| `s1_gamma3` | 1.017549 | 0.157031 | no |
| `s1_depth` | 0.0094715922 | 0.000932963 | no |
| `s1_int1` | 1.9016322 | 0.216356 | no |
| `s1_int2` | 1.6999283 | 0.197151 | no |
| `s2_delta` | 0.19577985 | 0.00491568 | no |
| `s2_quad` | -0.023056287 | 0.0092168 | no |
| `s2_bhf` | 49.562558 | 0.0319861 | no |
| `s2_gamma1` | 0.24186947 | 0.00758055 | no |
| `s2_gamma2` | 1 |  | sí |
| `s2_gamma3` | 1 |  | sí |
| `s2_depth` | 0.014650173 | 0.000275716 | no |
| `s2_int1` | 3 |  | sí |
| `s2_int2` | 2 |  | sí |

## δ corregido (referido a la calibración, iso_ref = -0.1084 mm/s)

- s1: δ corregido = 0.655427 mm/s
- s2: δ corregido = 0.30418 mm/s

## Resumen numérico residual

- Media residuo: 3.0724401e-06
- Desv. típica residuo: 0.0017439234
- Máximo |residuo|: 0.0039264653

## Texto del panel Estado

```text
Fichero: Fe3O4.adt
Canales leídos: 512
Folding point centro: 257.42647
Folding point Normos aprox.: 514.85295
Pares doblados: 254
Normalización: / 204561
Vmax = 11.966 mm/s
Base = 1.0002
Pendiente = 1.0568e-05
Sextetes activos: 1, 2
Ajuste velocidad: no
RMS ajuste: 0.00174393
χ² reducido: 1.34151  (χ²=319.28, gl=238)
AIC = 90.0984    BIC = 146.696    parámetros = 16
Diagnóstico residuo: lag1=0.315, runs z=-4.400, antisim=-0.164
Comparación de modelos: menor AIC/BIC es mejor si se ajustan los mismos datos.
Autoarranques probados: 9
Aviso residuo: parece tener estructura no aleatoria.
  Revisa modelo, folding point, calibración Vmax o componentes faltantes.
Calibración asociada sin incertidumbre explícita de Vmax. Considera error sistemático adicional.
Correlación máxima: |r|=0.859 entre s1_depth y s1_int1

Porcentaje de área por componente:
  Comp. 1 (Sextete): 32.928% ± 1.67%  área=0.0643219
  Comp. 2 (Sextete): 67.072% ± 1.67%  área=0.131017

Sextete 1: BHF=45.7576 T, δ=0.547027, ΔEQ=0.0548435
  Γ HWHM reales 1/2/3 = 0.2465 / 0.2236 / 0.2508
  FWHM equiv. 1/2/3 = 0.493 / 0.4472 / 0.5017
  Γ rel 2/3 = 0.9071 / 1.018
  prof=0.00947159, I reales=1.902, 1.7, 1
  δ corregido (calib iso=-0.1084) = 0.655427 mm/s
Sextete 2: BHF=49.5626 T, δ=0.19578, ΔEQ=-0.0230563
  Γ HWHM reales 1/2/3 = 0.2419 / 0.2419 / 0.2419
  FWHM equiv. 1/2/3 = 0.4837 / 0.4837 / 0.4837
  Γ rel 2/3 = 1 / 1
  prof=0.0146502, I reales=3, 2, 1
  δ corregido (calib iso=-0.1084) = 0.30418 mm/s

Fijados: s2_gamma2, s2_gamma3, s2_int1, s2_int2
```

---
Informe generado automáticamente. Revisar siempre residuos, calibración y sentido físico de los parámetros.
