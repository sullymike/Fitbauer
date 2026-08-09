# Third-party licenses / Licencias de terceros

Fitbauer itself is distributed under the **Apache License 2.0** (see [`LICENSE`](LICENSE)).
This file lists the third-party components that Fitbauer depends on, and — for the
binary builds — the components that are **bundled inside** the distributed executable.

> Fitbauer se distribuye bajo la **licencia Apache 2.0**. Este fichero enumera los
> componentes de terceros de los que depende y, en las versiones ejecutables, los que
> viajan **empaquetados dentro** del binario distribuido. El texto está en inglés por
> ser el uso habitual para avisos de licencia.

---

## Qt / PySide6 — LGPL v3 (important)

Fitbauer uses the **Qt** toolkit through the **Qt for Python (PySide6)** bindings.
PySide6, Shiboken6 and the Qt libraries they wrap are used here under the terms of the
**GNU Lesser General Public License, version 3 (LGPLv3)**.

- Copyright © The Qt Company Ltd. and other contributors.
- Home page: <https://www.qt.io/qt-for-python>
- Full licence text: [`licenses/LGPL-3.0.txt`](licenses/LGPL-3.0.txt), which incorporates
  by reference the GNU GPL v3, included as [`licenses/GPL-3.0.txt`](licenses/GPL-3.0.txt).
- Qt is also available under commercial terms and under the GPL; Fitbauer relies on the
  LGPLv3 option and does **not** modify Qt, PySide6 or Shiboken6 in any way.

### Replacing the Qt libraries (LGPLv3 §4)

The LGPLv3 grants the recipient the right to relink Fitbauer against a modified version
of Qt. Fitbauer is designed so this is straightforward:

- **Source / ZIP distribution.** Qt is not shipped at all: PySide6 is installed by the
  user with `pip install -r requirements.txt`. Any compatible PySide6/Qt build already in
  the environment is picked up automatically — nothing else to do.
- **PyInstaller executable.** Qt travels as ordinary **shared libraries**
  (`.so` / `.dll` / `.dylib`) inside the distribution directory (`Fitbauer/_internal/PySide6/…`
  in one-dir builds; extracted to a temporary directory at start-up in one-file builds).
  Replacing those files with a user-supplied build of the same Qt major version is enough
  to relink the application; no rebuild of Fitbauer is required. Prefer the **one-dir**
  build (`pyinstaller Fitbauer.spec`, which produces `dist/Fitbauer/`) if you intend to do
  this, since the libraries are then directly accessible on disk.
- The complete source of Fitbauer, including the build recipe (`Fitbauer.spec`), is public
  at <https://github.com/sullymike/Fitbauer>, so the application can also be rebuilt from
  scratch against any Qt version.

Unmodified sources of Qt, PySide6 and Shiboken6 are obtainable from The Qt Company
(<https://download.qt.io/>) and from PyPI (<https://pypi.org/project/PySide6/>).

---

## Runtime dependencies

| Component | Version required | Licence | Project |
|---|---|---|---|
| **PySide6** (Qt for Python) | ≥ 6.5 | LGPL-3.0-only *(or GPL-2.0/GPL-3.0, at the user's option)* | <https://www.qt.io/qt-for-python> |
| **Shiboken6** (pulled in by PySide6) | matches PySide6 | LGPL-3.0-only *(or GPL-2.0/GPL-3.0)* | <https://pypi.org/project/shiboken6/> |
| **NumPy** | ≥ 2.0 | BSD-3-Clause | <https://numpy.org> |
| **SciPy** | any | BSD-3-Clause | <https://scipy.org> |
| **Matplotlib** | any | Matplotlib licence (PSF-based, BSD-compatible) | <https://matplotlib.org> |
| **Requests** | any | Apache-2.0 | <https://requests.readthedocs.io> |

Installing the above also pulls in their own transitive dependencies. The ones that end up
inside a binary build are, at the time of writing:

| Component | Licence |
|---|---|
| certifi | MPL-2.0 |
| charset-normalizer | MIT |
| contourpy | BSD-3-Clause |
| cycler | BSD-3-Clause |
| fonttools | MIT |
| idna | BSD-3-Clause |
| kiwisolver | BSD-3-Clause |
| packaging | Apache-2.0 *or* BSD-2-Clause |
| pillow | MIT-CMU (HPND) |
| pyparsing | MIT |
| python-dateutil | Apache-2.0 *or* BSD-3-Clause |
| six | MIT |
| urllib3 | MIT |

Development and test-only dependencies (`requirements-dev.txt`) are not distributed:
**pytest** (MIT) and **pytest-qt** (MIT).

---

## Bundled in the executable builds only

| Component | Licence | Notes |
|---|---|---|
| **CPython** runtime | PSF License Agreement | Embedded by PyInstaller. <https://docs.python.org/3/license.html> |
| **PyInstaller bootloader** | GPL-2.0-or-later **with bootloader exception** | The exception explicitly allows bundling the bootloader with applications under any licence. <https://pyinstaller.org/en/stable/license.html> |

---

## Data and physical constants

The α-Fe reference velocity pattern (±0.839 / ±3.084 / ±5.329 mm/s at 33.0 T) and the
nuclear constants used by Fitbauer come from the published Mössbauer literature and are
factual data, not copyrightable material. Sample spectra in `data_sample/` were measured
or synthesised by the authors and are covered by the Apache-2.0 licence of the project.

Fitbauer can read files produced by **NORMOS** (R. A. Brand) and reproduces its file
formats and conventions for interoperability. No NORMOS code is included in, or derived
into, this repository.

---

*Last reviewed: 2026-08-09. If a dependency is added or upgraded, update this file and
the [`NOTICE`](NOTICE) alongside it.*
