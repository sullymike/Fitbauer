# Fitbauer v4.17.3

## Nuevo idioma: portugués 🇵🇹

Traducción completa al portugués (europeo, Acordo Ortográfico 1990) desde el
español:

- **Interfaz** — `locales/pt/strings.json`, las 803 claves de menús, paneles,
  diálogos y mensajes.
- **Ayuda integrada** — `locales/pt/help.json`, los 30 capítulos completos
  (espectroscopía, modos de ajuste, distribuciones, CLI…).
- Terminología revisada con glosario consistente (*Ficheiro, Dobragem, Desvio
  isomérico, Definições…*) y registro formal unificado.
- Los placeholders de formato y los grupos temáticos de la ayuda se
  verificaron idénticos a `es`; el test de paridad de locales cubre ahora
  **8 idiomas** (es, en, fr, de, pt, ru, ja, zh).

El idioma aparece automáticamente en **Vista → Idioma** y se incluye en los
ejecutables.

Suite completa: **310 tests en verde**.
