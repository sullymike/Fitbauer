"""Capturas de pantalla del artículo (docs/img/captura-*.png) con la ventana real.

Usa una configuración AISLADA (no toca ~/.config del usuario, igual que
tests/conftest.py), la interfaz en inglés y el layout «Tres columnas».

Uso:  QT_QPA_PLATFORM=offscreen python docs/article_screenshots.py SALIDA CONFIG_TMP [log10_alpha] [bins]
      (por defecto α = 10³ y 60 bins para la distribución bimodal)
La captura de distribución se monta luego con el gráfico (dist_canvas.png) a
la izquierda y el diálogo P(BHF) (dist_dialog.png) a la derecha.
"""
import sys, json, importlib
from pathlib import Path
ROOT = Path("/home/jorge/fitbauer/Mossbauer"); sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]); CFG = Path(sys.argv[2])
CFG.mkdir(exist_ok=True)
(CFG / "settings.json").write_text(json.dumps({"ui_language": "en", "plot_style": "classic",
                                                "check_updates_on_startup": False, "layout_preset": "Tres columnas"}))
from PySide6 import QtWidgets, QtCore
from PySide6.QtTest import QTest
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
# ── aislar configuración (igual que tests/conftest.py) ──
import core.data_io as data_io, core.param_overrides as po
for m, a, v in [(data_io, "CONFIG_DIR", CFG), (data_io, "SETTINGS_PATH", CFG/"settings.json"),
                (data_io, "CREDENTIALS_PATH", CFG/"credentials.json"),
                (po, "CONFIG_DIR", CFG), (po, "PARAM_LIMITS_PATH", CFG/"param_limits.json")]:
    setattr(m, a, v)
for name, attr in (("gui.layout_manager", "SETTINGS_PATH"), ("gui.session_io", "CONFIG_DIR"),
                   ("gui.updates", "CONFIG_DIR"), ("gui.fit_history", "HISTORY_PATH"), ("gui.help", "SETTINGS_PATH")):
    try:
        mod = importlib.import_module(name)
    except Exception:
        continue
    if hasattr(mod, attr):
        setattr(mod, attr, CFG if attr == "CONFIG_DIR" else CFG / ("fit_history.json" if attr == "HISTORY_PATH" else "settings.json"))
assert str(data_io.SETTINGS_PATH).startswith(str(CFG))
from PySide6.QtWidgets import QMessageBox
for n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: (print("AVISO:", *[x for x in a[1:] if isinstance(x, str)]), QMessageBox.StandardButton.Ok)[-1]))
import mossbauer_qt as mq
dialogs = []
QtWidgets.QDialog.exec = lambda self: (dialogs.append(self), self.show(), 0)[-1]

def window():
    w = mq.MossbauerQtWindow(); w.resize(1600, 1000); w.show(); QTest.qWait(400)
    return w
def settle(w):
    for _ in range(6): QTest.qWait(150); app.processEvents()

D = ROOT / "data_sample"
# 1) Ventana principal: calibración α-Fe ajustada
w = window()
w.load_session_file(D / "calibration_session.json"); settle(w)
w.on_fit(); settle(w)
w.grab().save(str(OUT / "captura-pantalla-principal.png"))
print("1 ok:", w.statusBar().currentMessage())
w.close()

# 2) Ajuste discreto de magnetita (solo el gráfico)
w = window()
w._load_file(D / "magnetita_Fe3O4.adt"); settle(w)
w.n_components_spin.setValue(2); settle(w)
tmpl = json.loads((D / "template_magnetita.json").read_text())
tmpl = tmpl.get("model_state", tmpl)
for cp in w.components_panels[:2]:
    for name, ctl in cp.params.items():
        key = f"s{cp.idx}_{name}"
        if key in tmpl["vars"]:
            ctl.set_value(float(tmpl["vars"][key]))
            ctl.set_fixed(bool(tmpl["fixed"].get(key, False)))
settle(w)
w.on_fit(); settle(w)
w.canvas.grab().save(str(OUT / "captura-ajuste-discreto.png"))
w.grab().save(str(OUT / "magnetita_ventana.png"))
print("2 ok:", w.statusBar().currentMessage())
w.close()

# 3) Distribución bimodal: gráfico + diálogo P(BHF)
w = window()
w.load_session_file(D / "sintetico_dist_bhf_bimodal_session.json"); settle(w)
w._load_file(D / "sintetico_dist_bhf_bimodal.adt"); settle(w)
w.dist_panel._set_log_alpha(float(sys.argv[3]) if len(sys.argv) > 3 else 3.0); w.dist_panel.nbins.set_value(int(sys.argv[4]) if len(sys.argv) > 4 else 60); settle(w)
dialogs.clear()
print("3 cargado:", w.file.velocity is not None, "modo", w.mode_combo.currentIndex(), "dist_mode", w.is_distribution_mode)
w.on_fit(); settle(w)
print("3 estado:", w.statusBar().currentMessage(), "res:", w.runtime_results.distribution_result is not None)
w.canvas.grab().save(str(OUT / "dist_canvas.png"))
w._show_distribution_dialog(w.runtime_results.distribution_result); settle(w)
pb = [d for d in dialogs if "P(" in d.windowTitle()]
print("3 diálogos:", [d.windowTitle() for d in dialogs])
if pb:
    pb[-1].resize(740, 480); settle(w); pb[-1].grab().save(str(OUT / "dist_dialog.png"))
w.close()
