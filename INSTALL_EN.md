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
git clone https://github.com/sullymike/Mossbauer.git
cd Mossbauer
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
python fitbauer.py        # Qt by default, falls back to Tk
```

## Alternative installer script

The repository includes an installation helper:

```bash
python install.py
```

It checks Python, installs dependencies and can create a launcher depending on the system.

## Updating

The program can check GitHub Releases from inside the GUI:

```text
Help → Check for updates...
```

The update channel can be configured as stable or beta if this option is enabled in the update settings.

## Main files

- `mossbauer_fe33_gui_v2IA.py`: main GUI.
- `mossbauer_help.py`: built-in help in Spanish and English.
- `mossbauer_distribution.py`: distribution-fitting tools.
- `mossbauer_updater.py`: update logic.
- `requirements.txt`: Python dependencies.

## Troubleshooting

If the GUI does not start, first check that the virtual environment is active and that dependencies were installed correctly:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m py_compile mossbauer_fe33_gui_v2IA.py mossbauer_help.py
```

If PDF report generation fails, the Markdown report is still saved. PDF export may require optional rendering libraries depending on the system.
