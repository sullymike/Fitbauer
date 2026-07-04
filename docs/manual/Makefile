# Manual de usuario de Fitbauer
#
#   make          -> genera figuras (si faltan) y compila main.pdf
#   make figures  -> (re)genera las figuras de física con matplotlib
#   make pdf       -> compila el PDF con latexmk (o pdflatex de reserva)
#   make clean     -> borra ficheros auxiliares de LaTeX
#   make distclean -> además borra main.pdf

ROOT   := ../..
PY     ?= python3
FIGDIR := img
FIGSCRIPT := scripts/make_figures.py
FIGS := $(FIGDIR)/fig_load_alphafe.pdf \
        $(FIGDIR)/fig_calibration_fit.pdf \
        $(FIGDIR)/fig_sim_components.pdf \
        $(FIGDIR)/fig_pbhf_distribution.pdf

.PHONY: all pdf figures clean distclean

all: figures pdf

figures: $(FIGS)

$(FIGS): $(FIGSCRIPT)
	cd $(ROOT) && $(PY) docs/manual/$(FIGSCRIPT)

pdf: main.tex
	@if command -v latexmk >/dev/null 2>&1; then \
		latexmk -pdf -silent main.tex ; \
	else \
		pdflatex -interaction=nonstopmode main.tex && \
		pdflatex -interaction=nonstopmode main.tex ; \
	fi

clean:
	@if command -v latexmk >/dev/null 2>&1; then latexmk -c >/dev/null 2>&1 || true; fi
	rm -f main.aux main.log main.out main.toc main.fls main.fdb_latexmk \
	      chapters/*.aux

distclean: clean
	rm -f main.pdf
