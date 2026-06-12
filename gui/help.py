"""Ayuda integrada y diálogo Acerca de de la GUI Qt."""
from __future__ import annotations

import html
import re

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr, get_language
from mossbauer_help import get_help_sections, get_help_groups
from core.constants import APP_NAME, APP_VERSION
from core.data_io import SETTINGS_PATH
from gui.branding import _logo_pixmap


class HelpMixin:
    @staticmethod
    def _help_format_content(content: str) -> str:
        """Convierte el texto plano de un capítulo de ayuda en HTML enriquecido.

        Reconoce subtítulos en una línea acabada en dos puntos (``X:``) seguidos
        de bloque sangrado, viñetas (``•``, ``-`` o ``  número.``) y aplica
        ``**bold**``, ``*italic*`` y `` `code` `` inline. También resalta en
        **negrita** automáticamente las etiquetas de menús y submenús del
        programa (Archivo, Cargar..., Ajustar, etc.) para que el lector
        identifique a qué control se refiere cada explicación.
        """
        text = content.strip("\n")
        menu_pattern = HelpMixin._help_menu_pattern()

        def _inline(s: str) -> str:
            s = html.escape(s)
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", s)
            s = re.sub(r"`([^`]+)`",
                       r"<code style='background:#f1f5f9;color:#0f172a;"
                       r"padding:1px 4px;border-radius:3px;'>\1</code>", s)
            if menu_pattern is not None:
                s = menu_pattern.sub(
                    lambda m: (
                        m.group(0)
                        if (m.string[max(0, m.start() - 4):m.start()].endswith(("<b>", "<i>"))
                            or "<b>" in m.group(0)
                            or "<i>" in m.group(0))
                        else f"<b>{m.group(0)}</b>"
                    ),
                    s,
                )
            return s

        parts: list[str] = []
        lines = text.split("\n")
        i, n = 0, len(lines)

        def _indent(raw_line: str) -> int:
            return len(raw_line) - len(raw_line.lstrip(" \t"))

        def _is_bullet(raw_line: str) -> bool:
            return (
                re.match(r"^\s*[•\-]\s+", raw_line) is not None
                or re.match(r"^\s*\d+\.\s+", raw_line) is not None
            )

        def _is_menu_item_start(pos: int) -> bool:
            """Detecta bloques sangrados de tipo ``Submenú`` + ``Campo: texto``.

            Gran parte de la ayuda replica la estructura de los menús como::

                Cargar...
                  Qué es: ...
                  Para qué sirve: ...

            Si se tratan como párrafos normales, Qt los fusiona en una línea
            larga. Este detector conserva la jerarquía visual del texto fuente.
            """
            if pos + 1 >= n:
                return False
            current = lines[pos]
            stripped_current = current.strip()
            if (
                not stripped_current
                or stripped_current.endswith(":")
                or _is_bullet(current)
                or _indent(current) == 0
                or len(stripped_current) > 90
            ):
                return False
            nxt = lines[pos + 1]
            stripped_next = nxt.strip()
            if not stripped_next or _indent(nxt) <= _indent(current):
                return False
            return re.match(r"^[^:]{2,36}:\s+.+", stripped_next) is not None

        def _render_menu_item(pos: int) -> tuple[str, int]:
            base_indent = _indent(lines[pos])
            title = lines[pos].strip()
            rows: list[tuple[str, str]] = []
            j = pos + 1
            while j < n:
                raw_line = lines[j]
                stripped_line = raw_line.strip()
                if not stripped_line:
                    break
                if _indent(raw_line) <= base_indent:
                    break
                match = re.match(r"^([^:]{2,36}):\s*(.*)$", stripped_line)
                if match:
                    rows.append((match.group(1).strip(), match.group(2).strip()))
                elif rows:
                    key, value = rows[-1]
                    rows[-1] = (key, f"{value} {stripped_line}".strip())
                else:
                    rows.append(("", stripped_line))
                j += 1
            if rows:
                body = "".join(
                    "<li style='margin:3px 0;'>"
                    + (f"<b>{_inline(key)}:</b> " if key else "")
                    + f"{_inline(value)}</li>"
                    for key, value in rows
                )
            else:
                body = ""
            html_block = (
                "<div style='margin:10px 0 12px 18px;padding:10px 12px;"
                "border-left:4px solid #38bdf8;background:#f8fafc;"
                "border-radius:6px;'>"
                f"<h5 style='color:#075985;font-size:1.02em;margin:0 0 6px 0;'>"
                f"{_inline(title)}</h5>"
                "<ul style='margin:0 0 0 20px;padding:0;line-height:1.45;'>"
                f"{body}</ul></div>"
            )
            return html_block, j

        while i < n:
            raw = lines[i]
            stripped = raw.strip()
            # Línea en blanco → separador de párrafos
            if not stripped:
                parts.append("")
                i += 1
                continue
            # Bloque de submenú/opción con campos descriptivos. Debe evaluarse
            # antes de los párrafos para no perder la sangría del help.json.
            if _is_menu_item_start(i):
                html_block, i = _render_menu_item(i)
                parts.append(html_block)
                continue
            # Subtítulo de tipo "Algo:" seguido de bloque sangrado o líneas
            if (
                stripped.endswith(":")
                and not stripped.startswith(("-", "•"))
                and len(stripped) <= 80
                and (i + 1 >= n or not lines[i + 1].strip()
                     or lines[i + 1].startswith((" ", "\t")))
            ):
                parts.append(
                    f"<h4 style='color:#0f766e;margin:14px 0 4px 0;'>"
                    f"{_inline(stripped[:-1])}</h4>"
                )
                i += 1
                continue
            # Viñetas y numeración con sangría
            if _is_bullet(raw):
                numbered = re.match(r"^\s*\d+\.\s+", raw) is not None
                tag = "ol" if numbered else "ul"
                items: list[str] = []
                while i < n and _is_bullet(lines[i]):
                    body = re.sub(r"^\s*(?:[•\-]\s+|\d+\.\s+)", "", lines[i])
                    items.append(f"<li>{_inline(body)}</li>")
                    i += 1
                parts.append(
                    f"<{tag} style='margin:4px 0 8px 22px;padding:0;"
                    "line-height:1.5;'>" + "".join(items) + f"</{tag}>"
                )
                continue
            # Párrafo normal: junta líneas hasta separador o cambio de tipo
            buf = [raw]
            i += 1
            while i < n and lines[i].strip() and not (
                _is_bullet(lines[i])
                or _is_menu_item_start(i)
                or lines[i].strip().endswith(":")
            ):
                buf.append(lines[i])
                i += 1
            joined = _inline(" ".join(s.strip() for s in buf))
            parts.append(f"<p style='margin:6px 0;line-height:1.55;'>{joined}</p>")
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _help_menu_pattern() -> "re.Pattern | None":
        """Construye un patrón con las etiquetas de menús/submenús del programa.

        Memoizado por idioma: lee los valores de las claves ``menu.*``,
        ``file.*``, ``fit.*``, ``options.*``, ``view.*`` y un subconjunto
        seguro de ``help.*`` del catálogo actual y los compone como un único
        regex case-insensitive (los términos más largos antes para que
        ``Ajustar Vmax con el patrón`` gane a ``Ajustar``).
        """
        from mossbauer_i18n import CATALOGS, get_language
        lang = get_language()
        cache = getattr(HelpMixin, "_help_menu_pattern_cache", {})
        if lang in cache:
            return cache[lang]
        catalog = CATALOGS.get(lang, {})
        prefixes = ("menu.", "file.", "fit.", "options.", "view.")
        help_allow = {
            "help.open", "help.about", "help.changelog",
            "help.check_updates", "help.configure_updates",
        }
        # Vocabulario común que jamás queremos en negrita aunque aparezca
        # como traducción (por ejemplo "Idioma" o "Lengua", "Tema", "sí/no").
        blacklist = {
            tr("yes", default="sí"), tr("no", default="no"),
            tr("menu.language", default="Idioma"),
            tr("help.language_label", default="Idioma:").rstrip(":"),
        }
        terms: set[str] = set()
        for k, v in catalog.items():
            if not isinstance(v, str):
                continue
            if not (k.startswith(prefixes) or k in help_allow):
                continue
            s = v.strip()
            # Saltar valores con placeholders ({...}) o demasiado largos
            if "{" in s or "}" in s or len(s) > 60 or len(s) < 3:
                continue
            if s in blacklist:
                continue
            # Una palabra de longitud < 4 suele ser demasiado genérica
            if " " not in s and len(s) < 4:
                continue
            terms.add(s)
            # Para etiquetas de varias palabras, añade también la versión sin
            # elipsis/dos-puntos para capturar referencias en el texto que
            # omiten esos signos ("Restricciones entre parámetros").
            stripped = s.rstrip(" .…:")
            if stripped != s and stripped.count(" ") >= 1 and len(stripped) >= 6:
                terms.add(stripped)
        if not terms:
            cache[lang] = None
            HelpMixin._help_menu_pattern_cache = cache
            return None
        # Ordena por longitud descendente y construye alternancia
        ordered = sorted(terms, key=lambda t: (-len(t), t))
        pat = "|".join(re.escape(t) for t in ordered)
        # Case-sensitive a propósito: las etiquetas de menú están capitalizadas
        # (Archivo, Ajustar, Opciones), así que evitamos resaltar el sustantivo
        # genérico en minúsculas ("ajuste", "archivo"…). El borde por delante
        # es blando porque varias etiquetas acaban en "…", "..." o ":".
        compiled = re.compile(rf"(?<![\w&]){pat}")
        cache[lang] = compiled
        HelpMixin._help_menu_pattern_cache = cache
        return compiled

    @staticmethod
    def _help_groups_order() -> list[tuple[str, str]]:
        """Orden y etiqueta de los grupos temáticos del árbol de ayuda.

        Devuelve ``[(group_code, etiqueta_traducida), ...]``. Cada capítulo de
        ``help.json`` lleva su propio campo ``group`` con uno de estos códigos,
        de modo que el agrupamiento es **independiente del idioma, del número
        de capítulos y de su orden** (antes se usaban índices fijos que se
        descolocaban al diferir las traducciones).
        """
        return [
            ("overview",      tr("help.tree_overview", default="🚀 Overview")),
            ("files",         tr("help.tree_files",    default="📁 Files and data")),
            ("fitting",       tr("help.tree_fitting",  default="🧮 Fitting")),
            ("distributions", tr("help.tree_distrib",
                               default="📊 Distributions P(BHF) / P(ΔEQ)")),
            ("results",       tr("help.tree_results",  default="💾 Results and reports")),
            ("tools",         tr("help.tree_tools",    default="🧰 Tools and extras")),
        ]

    def _help_layout(self) -> list[tuple[str, list[int]]]:
        """Construye la distribución jerárquica de la ayuda agrupando por el
        campo ``group`` de cada capítulo del idioma activo.

        Cada grupo conserva los capítulos en su orden natural dentro del
        ``help.json``. Devuelve ``[(etiqueta_grupo, [índices]), ...]`` para que
        el constructor del árbol no dependa de un mapeo de índices fijo.
        """
        groups = get_help_groups(get_language())
        layout: list[tuple[str, list[int]]] = []
        for code, label in self._help_groups_order():
            indices = [i for i, g in enumerate(groups) if g == code]
            if indices:
                layout.append((label, indices))
        return layout

    def on_help(self, show_shortcuts: bool = False) -> None:
        if self._help_dialog is not None:
            self._help_dialog.show()
            self._help_dialog.raise_()
            self._help_dialog.activateWindow()
            if show_shortcuts:
                tab_w = self._help_dialog.findChild(QtWidgets.QTabWidget)
                if tab_w is not None:
                    tab_w.setCurrentIndex(1)
            return

        calib_state = self.calib.to_view_state()
        sections = get_help_sections(
            voigt_sigma=calib_state.voigt_sigma,
            settings_path=SETTINGS_PATH,
            lang=get_language(),
        )
        dlg = QtWidgets.QDialog(self)
        dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        dlg.setModal(False)
        dlg.setWindowModality(QtCore.Qt.NonModal)
        dlg.destroyed.connect(lambda _obj=None: setattr(self, "_help_dialog", None))
        self._help_dialog = dlg
        dlg.setWindowTitle(tr("help.window_title"))
        dlg.resize(1180, 760)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(14, 12, 14, 10)
        v.setSpacing(8)
        header = QtWidgets.QLabel(f"<h2 style='margin:0;'>{tr('help.header_title')}</h2>")
        header.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(header)

        # ── Tab widget: Ayuda + Atajos ──────────────────────────────────
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.setStyleSheet(
            "QTabBar::tab { padding: 6px 18px; font-size: 10.5pt; }"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

        # ── Tab 1: Ayuda ────────────────────────────────────────────────
        help_tab = QtWidgets.QWidget()
        help_v = QtWidgets.QVBoxLayout(help_tab)
        help_v.setContentsMargins(0, 8, 0, 0)
        help_v.setSpacing(8)

        # Buscador
        search_row = QtWidgets.QHBoxLayout()
        search_lbl = QtWidgets.QLabel(tr("help.search_label", default="🔍 Buscar:"))
        search_edit = QtWidgets.QLineEdit()
        search_edit.setPlaceholderText(
            tr("help.search_placeholder",
               default="Filtra los capítulos y resalta los aciertos…")
        )
        search_count = QtWidgets.QLabel("")
        search_count.setStyleSheet("color:#475569;")
        search_row.addWidget(search_lbl)
        search_row.addWidget(search_edit, stretch=1)
        search_row.addWidget(search_count)
        help_v.addLayout(search_row)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        tree = QtWidgets.QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(18)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(False)
        tree.setAnimated(True)
        tree.setStyleSheet(
            "QTreeWidget { font-size: 10.5pt; background:#f8fafc;"
            " border:1px solid #e2e8f0; border-radius:6px; padding:4px; }"
            "QTreeWidget::item { padding: 4px 4px; }"
            "QTreeWidget::item:selected { background:#dbeafe; color:#1e40af; }"
        )
        tree.setMinimumWidth(320)
        tree.setMaximumWidth(380)

        group_items: list[QtWidgets.QTreeWidgetItem] = []
        leaves: list[QtWidgets.QTreeWidgetItem] = []
        seen: set[int] = set()
        n_total = len(sections)
        for grp_label, indices in self._help_layout():
            top = QtWidgets.QTreeWidgetItem(tree, [grp_label])
            font = top.font(0)
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() + 0.5)
            top.setFont(0, font)
            top.setForeground(0, QtGui.QBrush(QtGui.QColor("#1e3a8a")))
            top.setFlags(top.flags() & ~QtCore.Qt.ItemIsSelectable)
            for idx in indices:
                if 0 <= idx < n_total and idx not in seen:
                    seen.add(idx)
                    leaf = QtWidgets.QTreeWidgetItem(top, [sections[idx][0]])
                    leaf.setData(0, QtCore.Qt.UserRole, idx)
                    leaves.append(leaf)
            group_items.append(top)
        unassigned = [i for i in range(n_total) if i not in seen]
        if unassigned:
            other = QtWidgets.QTreeWidgetItem(
                tree, [tr("help.tree_other", default="📚 Otros")]
            )
            font = other.font(0); font.setBold(True); other.setFont(0, font)
            other.setFlags(other.flags() & ~QtCore.Qt.ItemIsSelectable)
            for idx in unassigned:
                leaf = QtWidgets.QTreeWidgetItem(other, [sections[idx][0]])
                leaf.setData(0, QtCore.Qt.UserRole, idx)
                leaves.append(leaf)
            group_items.append(other)
        tree.expandAll()
        split.addWidget(tree)

        text_w = QtWidgets.QTextBrowser()
        text_w.setOpenExternalLinks(True)
        text_w.setStyleSheet(
            "QTextBrowser { font-family: -apple-system, Segoe UI, sans-serif;"
            " font-size: 10.8pt; padding: 14px 18px;"
            " border:1px solid #e2e8f0; border-radius:6px; background:white; }"
        )
        split.addWidget(text_w)
        split.setSizes([340, 840])
        help_v.addWidget(split, stretch=1)
        tab_widget.addTab(help_tab, tr("help.tab_help", default="📖 Ayuda"))

        def _render(idx: int, highlight: str = "") -> None:
            if not (0 <= idx < len(sections)):
                return
            title, heading, content = sections[idx]
            body = self._help_format_content(content)
            css = (
                "h2{color:#1e40af;margin:0 0 4px 0;}"
                "h3{color:#475569;margin:0 0 14px 0;font-weight:500;"
                "border-bottom:1px solid #e2e8f0;padding-bottom:6px;}"
                "h4{color:#0f766e;margin:14px 0 4px 0;}"
                "p,li{color:#1f2937;}"
                "mark{background:#fde68a;color:#7c2d12;border-radius:2px;padding:0 1px;}"
            )
            html_doc = (
                f"<style>{css}</style>"
                f"<h2>{html.escape(title)}</h2>"
                f"<h3>{html.escape(heading)}</h3>{body}"
            )
            if highlight:
                pat = re.compile(re.escape(highlight), re.IGNORECASE)

                def _highlight_outside_tags(s: str) -> str:
                    out, buf = [], []
                    i, n = 0, len(s)
                    while i < n:
                        ch = s[i]
                        if ch == "<":
                            if buf:
                                out.append(pat.sub(
                                    lambda m: f"<mark>{m.group(0)}</mark>",
                                    "".join(buf)))
                                buf = []
                            j = s.find(">", i)
                            if j == -1:
                                out.append(s[i:]); break
                            out.append(s[i:j + 1]); i = j + 1
                        else:
                            buf.append(ch); i += 1
                    if buf:
                        out.append(pat.sub(
                            lambda m: f"<mark>{m.group(0)}</mark>",
                            "".join(buf)))
                    return "".join(out)

                html_doc = _highlight_outside_tags(html_doc)
            text_w.setHtml(html_doc)

        def _on_tree(curr: QtWidgets.QTreeWidgetItem, _prev) -> None:
            if curr is None:
                return
            data = curr.data(0, QtCore.Qt.UserRole)
            if data is not None:
                _render(int(data), search_edit.text().strip())
            elif curr.childCount() > 0:
                child = curr.child(0)
                tree.setCurrentItem(child)

        tree.currentItemChanged.connect(_on_tree)
        if leaves:
            tree.setCurrentItem(leaves[0])

        def _apply_filter() -> None:
            q = search_edit.text().strip().lower()
            visible = 0
            for grp_item in group_items:
                grp_has = False
                for ch_idx in range(grp_item.childCount()):
                    leaf = grp_item.child(ch_idx)
                    data = leaf.data(0, QtCore.Qt.UserRole)
                    if data is None:
                        continue
                    title, heading, content = sections[int(data)]
                    hay = (
                        not q
                        or q in title.lower()
                        or q in heading.lower()
                        or q in content.lower()
                    )
                    leaf.setHidden(not hay)
                    if hay:
                        visible += 1
                        grp_has = True
                grp_item.setHidden(not grp_has)
            if q:
                search_count.setText(
                    tr("help.search_count", default="{n} capítulos").format(n=visible)
                )
            else:
                search_count.setText("")
            curr = tree.currentItem()
            if curr is not None and curr.data(0, QtCore.Qt.UserRole) is not None:
                _render(int(curr.data(0, QtCore.Qt.UserRole)), q)

        search_edit.textChanged.connect(lambda _t: _apply_filter())

        # ── Tab 2: Atajos de teclado ────────────────────────────────────
        tab_widget.addTab(
            self._build_shortcuts_editor(dlg),
            tr("help.tab_shortcuts", default="⌨️ Atajos"),
        )

        v.addWidget(tab_widget, stretch=1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.close)
        v.addWidget(bb)

        if show_shortcuts:
            tab_widget.setCurrentIndex(1)

        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _build_shortcuts_editor(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Construye el panel de edición de atajos de teclado."""
        from collections import Counter
        from gui.menu_builder import SHORTCUT_REGISTRY

        w = QtWidgets.QWidget(parent)
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(10)

        info = QtWidgets.QLabel(
            tr("shortcuts.info",
               default="Haz clic en el campo de atajo y pulsa la combinación de "
                       "teclas que quieras asignar. Pulsa Supr o Retroceso dentro "
                       "del campo para borrar un atajo. Los cambios se aplican al "
                       "guardar y se conservan entre sesiones.")
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#475569; font-size:10pt; padding:4px 0;")
        lay.addWidget(info)

        table = QtWidgets.QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([
            tr("shortcuts.col_menu",     default="Menú"),
            tr("shortcuts.col_action",   default="Acción"),
            tr("shortcuts.col_shortcut", default="Atajo actual"),
            tr("shortcuts.col_default",  default="Predeterminado"),
        ])
        table.setRowCount(len(SHORTCUT_REGISTRY))
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(
            "QTableWidget { font-size:10.5pt; border:1px solid #e2e8f0;"
            " border-radius:6px; }"
            "QTableWidget::item { padding:2px 6px; }"
            "QHeaderView::section { background:#f1f5f9; font-weight:bold;"
            " padding:6px; border:none; border-bottom:1px solid #cbd5e1; }"
        )

        current_shortcuts = dict(getattr(self, "_custom_shortcuts", {}))
        seq_edits: list[tuple[str, QtWidgets.QKeySequenceEdit]] = []

        for row, (action_id, menu_key, action_key, default) in enumerate(SHORTCUT_REGISTRY):
            for col, text in enumerate((tr(menu_key), tr(action_key))):
                item = QtWidgets.QTableWidgetItem(text)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, col, item)

            seq_edit = QtWidgets.QKeySequenceEdit()
            current = current_shortcuts.get(action_id, default)
            seq_edit.setKeySequence(QtGui.QKeySequence(current))
            seq_edit.setToolTip(
                tr("shortcuts.tooltip", default="Haz clic y pulsa la combinación de teclas")
            )
            table.setCellWidget(row, 2, seq_edit)
            seq_edits.append((action_id, seq_edit))

            def_item = QtWidgets.QTableWidgetItem(default)
            def_item.setFlags(def_item.flags() & ~QtCore.Qt.ItemIsEditable)
            def_item.setForeground(QtGui.QBrush(QtGui.QColor("#94a3b8")))
            table.setItem(row, 3, def_item)

        table.resizeRowsToContents()
        lay.addWidget(table, stretch=1)

        # Botones
        btn_row = QtWidgets.QHBoxLayout()
        btn_reset = QtWidgets.QPushButton(
            tr("shortcuts.reset_all", default="Restablecer todos")
        )
        btn_reset.setToolTip(
            tr("shortcuts.reset_tooltip", default="Vuelve a los atajos originales de fábrica")
        )
        btn_save = QtWidgets.QPushButton(
            tr("shortcuts.save", default="Guardar atajos")
        )
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton { background:#1d4ed8; color:white; padding:6px 18px;"
            " border-radius:5px; font-weight:bold; }"
            "QPushButton:hover { background:#1e40af; }"
        )

        def _reset_all() -> None:
            for action_id, seq_edit in seq_edits:
                dflt = next((d for a, _, _, d in SHORTCUT_REGISTRY if a == action_id), "")
                seq_edit.setKeySequence(QtGui.QKeySequence(dflt))

        def _save_shortcuts() -> None:
            # Atajo efectivo de cada acción (lo que el usuario ve ahora en su
            # campo) y, aparte, solo las desviaciones respecto al valor de
            # fábrica para persistirlas.
            effective: dict[str, str] = {}
            new_shortcuts: dict[str, str] = {}
            for action_id, seq_edit in seq_edits:
                ks = seq_edit.keySequence().toString()
                dflt = next((d for a, _, _, d in SHORTCUT_REGISTRY if a == action_id), "")
                effective[action_id] = ks
                if ks != dflt:
                    new_shortcuts[action_id] = ks
            # Detección de conflictos sobre TODOS los atajos efectivos no vacíos
            # (incluye choques con los predeterminados que no se han tocado).
            counts = Counter(v for v in effective.values() if v)
            dups = sorted(k for k, c in counts.items() if c > 1)
            if dups:
                QtWidgets.QMessageBox.warning(
                    w,
                    tr("shortcuts.conflict_title", default="Conflicto de atajos"),
                    tr("shortcuts.conflict_msg",
                       default="Hay atajos asignados a más de una acción: {keys}. "
                               "Corrígelos antes de guardar.").format(keys=", ".join(dups)),
                )
                return
            self._apply_custom_shortcuts(new_shortcuts)
            self._save_settings()
            QtWidgets.QMessageBox.information(
                w,
                tr("shortcuts.saved_title", default="Atajos guardados"),
                tr("shortcuts.saved_msg",
                   default="Los atajos de teclado se han guardado y aplicado."),
            )

        btn_reset.clicked.connect(_reset_all)
        btn_save.clicked.connect(_save_shortcuts)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)
        return w

    def on_about(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.about_title", version=APP_VERSION))
        v = QtWidgets.QVBoxLayout(dlg); v.setContentsMargins(24, 20, 24, 20)
        _pix = _logo_pixmap(110)
        if _pix is not None:
            logo = QtWidgets.QLabel(); logo.setPixmap(_pix)
            logo.setAlignment(QtCore.Qt.AlignCenter)
            v.addWidget(logo)
        title = QtWidgets.QLabel(f"<h2>{APP_NAME}</h2>"); title.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(title)
        v.addWidget(QtWidgets.QLabel(
            f"<center>{tr('splash.version', version=APP_VERSION)}<br>"
            f"<i>{tr('main.subtitle')}</i></center>"))
        v.addSpacing(8)
        v.addWidget(QtWidgets.QLabel(
            f"<center><i>{tr('splash.click_to_continue')}</i></center>"))
        dlg.mousePressEvent = lambda _e: dlg.accept()
        dlg.exec()
