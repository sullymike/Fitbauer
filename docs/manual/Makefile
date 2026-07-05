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
APXSCRIPT := scripts/make_appendix_figures.py
FIGS := $(FIGDIR)/fig_load_alphafe.pdf \
        $(FIGDIR)/fig_calibration_fit.pdf \
        $(FIGDIR)/fig_sim_components.pdf \
        $(FIGDIR)/fig_pbhf_distribution.pdf
APXFIGS := $(FIGDIR)/apx_lineshapes.pdf \
        $(FIGDIR)/apx_zeeman.pdf \
        $(FIGDIR)/apx_regularization.pdf \
        $(FIGDIR)/apx_relaxation.pdf \
        $(FIGDIR)/apx_thickness.pdf \
        $(FIGDIR)/apx_texture.pdf \
        $(FIGDIR)/apx_losses.pdf \
        $(FIGDIR)/apx_is.pdf \
        $(FIGDIR)/apx_2d_contour.pdf \
        $(FIGDIR)/apx_neel.pdf \
        $(FIGDIR)/apx_quadrupole.pdf \
        $(FIGDIR)/apx_powder.pdf \
        $(FIGDIR)/apx_lsurface.pdf \
        $(FIGDIR)/apx_relax_phenom.pdf \
        $(FIGDIR)/apx_profile.pdf \
        $(FIGDIR)/apx_multistart.pdf \
        $(FIGDIR)/apx_vbf.pdf

.PHONY: all pdf figures clean distclean

all: figures pdf

figures: $(FIGS) $(APXFIGS)

$(FIGS): $(FIGSCRIPT)
	cd $(ROOT) && $(PY) docs/manual/$(FIGSCRIPT)

$(APXFIGS): $(APXSCRIPT)
	cd $(ROOT) && $(PY) docs/manual/$(APXSCRIPT)

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
