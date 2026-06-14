## Fitbauer v4.10.1

Versión centrada en **identificación de fases**, **historial de ajustes persistente** y una ampliación importante de la **documentación**.

### ✨ Sugeridor de fases

- Identificación **bidireccional** a partir de los parámetros hiperfinos (δ, ΔEQ, B_hf) de cada componente, comparando contra una base de datos de referencia:
  - **Al inicio:** tras *Inicializar desde mínimos*, propone fases compatibles y permite, opcionalmente, **sembrar el ajuste** con sus valores de referencia.
  - **Tras el ajuste:** *Ajuste → Preparación → Identificar fases…* lista las fases compatibles, con su cita bibliográfica.
- **Interruptor maestro** *«Predicción de fases»*, **desactivado por defecto**.

### 🗂️ Historial de ajustes

- Cada ajuste terminado se guarda con hora, fichero, modo, χ²/χ²ᵣ, resumen de componentes y un snapshot completo **restaurable**.
- **Persistente** (sobrevive al reinicio) y con **tope configurable** (50 por defecto, rango 1–500).

### 📊 Base de datos de referencia

- Parámetros Mössbauer de referencia (δ, ΔEQ, B_hf) para fases de hierro, con procedencia bibliográfica (JSON + TSV + parser reproducible).

### 📚 Documentación

- Documentos matemáticos corregidos, ampliados y **traducidos al inglés** (manual, ajuste, distribuciones 1D/2D/IS, corrección de espesor, relajación).
- **Nuevos**: plegado, ajuste en serie, calibración α-Fe 33 T, comparación de espectros, formato de sesión, detección de mínimos (CWT) y perfil de verosimilitud — en ES y EN.
- Corregida la documentación de relajación (NeelSize y ajuste multi-temperatura ya implementados).

---

**Changelog completo:** ver `CHANGELOG.md`.
