# Installation guide · Mössbauer Fe-57 GUI

This guide explains how to install and run the Python version of the Mössbauer Fe-57 GUI.

Spanish version: [`INSTALL.md`](INSTALL.md)

## Requirements

- Python 3.10 or newer recommended.
- `pip`.
- Internet connection for installing dependencies and checking updates.

## Installation from source

Clone or download the repository and enter the project directory:

```bash
git clone https://github.com/sullymike/Fitbauer.git
cd Fitbauer
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python fitbauer.py        # Qt interface
```

## Alternative installer script

The repository includes an installation helper:

```bash
python install.py               # full install + register in the app menus
python install.py --menu-only   # only register the app in the menus
python install.py --no-menu     # install without touching the menus
python install.py --uninstall   # remove the menu entry
```

It checks Python, installs dependencies, creates a launcher, and **registers
Fitbauer in the system application menus** (per-user, no administrator rights) so
it can be launched from the menu with its icon:

- Linux: `~/.local/share/applications/fitbauer.desktop` (*Education* category, plus
  the icon under `hicolor`).
- Windows: a shortcut inside a *Fitbauer* Start Menu folder
  (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Fitbauer\Fitbauer.lnk`).

## Updating

The program can check GitHub Releases from inside the GUI:

```text
Help → Check for updates...
```

The update channel can be configured as stable or beta if this option is enabled in the update settings.

## Main files

- `mossbauer_qt.py`: main GUI (Qt/PySide6).
- `mossbauer_fit_cli.py` + `core/session.py`: headless command-line fitting.
- `mossbauer_help.py`: built-in help in Spanish and English.
- `mossbauer_distribution.py`: distribution-fitting tools.
- `mossbauer_updater.py`: update logic.
- `requirements.txt`: Python dependencies.

## Troubleshooting

If the GUI does not start, first check that the virtual environment is active and that dependencies were installed correctly:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m py_compile mossbauer_qt.py mossbauer_help.py
```

If PDF report generation fails, the Markdown report is still saved. PDF export may require optional rendering libraries depending on the system.
