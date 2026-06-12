<p align="center">
  <img src="assets/fitbauer_icon.png" alt="Fitbauer" width="140">
</p>

<h1 align="center">Fitbauer</h1>

<p align="center"><b>Software for Mössbauer spectrum fitting and analysis.</b></p>

<p align="center">
  <a href="README.md">🇬🇧 English version (main README)</a>
</p>

Programa de escritorio estable para cargar, doblar, simular y ajustar espectros Mössbauer de Fe-57.

Versión estable actual: **v4.8.1**  
Arranque: `python fitbauer.py`  
Ajuste por línea de comandos (headless): `mossbauer_fit_cli.py`

**Autores:** Jorge Sánchez Marcos · Nieves Menéndez González  
Departamento de Química Física · UAM

---

## Funciones principales

- Carga local de `.ws5` y `.adt`; descarga de espectros y calibraciones desde la web del laboratorio.
- Doblado del espectro con folding point fraccionario/interpolado (compatible con NORMOS).
- **Ajuste cristalino** — singletes, dobletes y sextetes; perfiles Lorentziano/Voigt; verosimilitud Poisson o Gauss; pérdida robusta; χ²/AIC/BIC.
- **Arranques múltiples** configurables y errores bootstrap Monte Carlo.
- **Intervalos de confianza por verosimilitud perfilada** con escaneo adaptativo.
- **Ajuste de distribuciones** — `P(BHF)`, `P(ΔEQ)`, `P(IS)` y tres modos 2D; regularización Hesse-Rübartsch; L-curve; componentes nítidos simultáneos.
- Cuadrupolo avanzado: primer orden, Kündig fijo, Kündig polvo; textura de intensidades de sextete.
- Presets físicos de restricciones (3:2:1 polvo, anchuras ligadas, δ/Γ atados entre componentes).
- Modelos de relajación: fenomenológico, Blume–Tjon dos estados, Néel–Arrhenius con distribución lognormal de tamaños.
- Límites de parámetros configurables desde la GUI (Vista → Límites de parámetros…).
- Figura Plotly interactiva con editor semi-manual de mínimos.
- Ajuste en serie (batch) con warm-start.
- Exportación del ajuste como TSV con **subespectros por componente** y cabecera informativa.
- Informes Markdown/PDF: informe completo e informe reducido.
- Guardado/carga de sesión JSON completa; ajustes persistentes entre arranques.
- Comprobación de actualizaciones y descarga desde GitHub Releases.
- Interfaz y ayuda integrada en **inglés**, español y francés.

---

## Capturas del programa

### Pantalla principal

<img src="docs/img/captura-pantalla-principal.png" alt="Pantalla principal de Fitbauer" width="900">

### Ajuste discreto

<img src="docs/img/captura-ajuste-discreto.png" alt="Ajuste discreto con dos dobletes, áreas y residuos" width="900">

### Distribución P(BHF)

<img src="docs/img/captura-distribucion-bhf.png" alt="Distribución de campo hiperfino P(BHF) con componentes nítidos" width="900">

### L-curve de regularización

<img src="docs/img/captura-lcurve.png" alt="L-curve para elegir el parámetro de regularización α" width="900">

### Informe Markdown/PDF

<img src="docs/img/captura-informe-markdown-pdf.png" alt="Informe PDF condensado con parámetros y figura" width="900">

---

## Arranque rápido

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python fitbauer.py
```

Prueba los datos de ejemplo:

1. **Archivo → Cargar…** → `data_sample/magnetita_Fe3O4.adt`
2. **Archivo → Cargar sesión…** → `data_sample/Fe3O4_session.json`

Flujo rápido:

```
Cargar espectro → revisar folding/Vmax → elegir modelo → ajustar
  → revisar residuos/áreas → exportar sesión/informe
```

---

## Instalación

Consulta [`INSTALL.md`](INSTALL.md) para instrucciones completas.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python fitbauer.py
```

Construir ejecutable con PyInstaller:

```bash
pyinstaller Fitbauer.spec    # → dist/Fitbauer/
```

---

## Historial de cambios

Consulta [`CHANGELOG.md`](CHANGELOG.md).
