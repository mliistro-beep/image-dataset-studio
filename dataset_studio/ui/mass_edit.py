# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Mass Tag Editor & Cleaner: logica dello script originale, testi localizzati, avviso sulle modifiche non salvate."""
import os
from collections import Counter
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton,
    QComboBox, QLineEdit, QTextEdit, QFileDialog, QMessageBox, QSplitter,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView
)

from ..config import IMAGE_EXTENSIONS, MASS_EDIT_TEMP_DIR
from ..dataset import layout
from ..dataset.archive import archive_filter, archive_stem, extract_archive, write_zip
from ..i18n import tr
from .widgets import NumericTableWidgetItem, ThumbnailLoader, ZoomableImageView


class MassEditWidget(QWidget):
    """Pannello dedicato alla manipolazione in massa (Mass Edit & Tag Cleaner) del dataset."""
    log_signal = Signal(str)
    dataset_updated_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_folder = ""
        self.image_files = []
        self.dataset_data = {}  # {filename: [list_of_tags]}
        self.tag_counter: Counter[str] = Counter()
        self.selected_tag_filter = None
        self.checked_tags = set()   # spunte conservate anche per i tag nascosti dal filtro
        self.dirty = False          # modifiche in memoria non ancora scritte su disco
        self.archive_source = ""    # archivio d'origine, se il dataset è stato estratto da un archivio
        self.gallery_items = {}     # {filename: QListWidgetItem} della galleria filtrata
        self.thumbnails = ThumbnailLoader(64, self)
        self.thumbnails.loaded.connect(self._on_thumbnail_loaded)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Main Splitter: Sinistra (Tabella Tag & Bulk Tools) | Destra (Galleria Filtrata & Ispettore)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PANNELLO SINISTRO (Tabella Tag & Operazioni in Massa) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_dataset_stats = QLabel(tr("mass.no_dataset"))
        self.lbl_dataset_stats.setStyleSheet("font-weight: bold; color: #00e5ff;")
        left_layout.addWidget(self.lbl_dataset_stats, stretch=0)

        self.btn_load_folder = QPushButton(tr("mass.load_folder"))
        self.btn_load_folder.clicked.connect(self._on_click_load_folder)
        left_layout.addWidget(self.btn_load_folder)

        self.btn_load_archive = QPushButton(tr("mass.load_archive"))
        self.btn_load_archive.clicked.connect(self._on_click_load_archive)
        left_layout.addWidget(self.btn_load_archive)

        # Filtro e Ricerca Tag
        filter_group = QGroupBox(tr("mass.filter_box"))
        filter_layout = QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(6, 6, 6, 6)

        self.entry_search_tag = QLineEdit()
        self.entry_search_tag.setPlaceholderText(tr("mass.search_ph"))
        self.entry_search_tag.textChanged.connect(self._filter_tag_table)
        filter_layout.addWidget(self.entry_search_tag)

        self.btn_clear_search = QPushButton(tr("mass.reset_filter"))
        self.btn_clear_search.clicked.connect(self._clear_tag_filter)
        filter_layout.addWidget(self.btn_clear_search)

        left_layout.addWidget(filter_group)

        # Tabella Frequenza Tag
        table_group = QGroupBox(tr("mass.table_box"))
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(6, 6, 6, 6)

        self.table_tags = QTableWidget()
        self.table_tags.setColumnCount(4)
        self.table_tags.setHorizontalHeaderLabels(["[ ]", tr("mass.col_tag"), tr("mass.col_freq"), tr("mass.col_cover")])
        self.table_tags.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tags.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_tags.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tags.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tags.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_tags.setSortingEnabled(True)
        self.table_tags.itemSelectionChanged.connect(self._on_tag_table_selection_changed)
        self.table_tags.itemChanged.connect(self._on_tag_item_changed)

        table_layout.addWidget(self.table_tags)

        # Pulsanti Selezione Checkbox
        select_btns_layout = QHBoxLayout()
        btn_check_all = QPushButton(tr("mass.check_all"))
        btn_check_all.clicked.connect(lambda: self._set_all_checks(True))
        btn_uncheck_all = QPushButton(tr("mass.uncheck_all"))
        btn_uncheck_all.clicked.connect(lambda: self._set_all_checks(False))
        select_btns_layout.addWidget(btn_check_all)
        select_btns_layout.addWidget(btn_uncheck_all)
        table_layout.addLayout(select_btns_layout)

        left_layout.addWidget(table_group)

        # Operazioni in Massa (Bulk Tools)
        bulk_group = QGroupBox(tr("mass.bulk_box"))
        bulk_layout = QGridLayout(bulk_group)
        bulk_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        bulk_layout.setContentsMargins(6, 6, 6, 6)

        # Rinomina / Sostituisci
        bulk_layout.addWidget(QLabel(tr("mass.replace_tag")), 0, 0)
        self.entry_replace_old = QLineEdit()
        self.entry_replace_old.setPlaceholderText(tr("mass.old_tag_ph"))
        bulk_layout.addWidget(self.entry_replace_old, 0, 1)

        self.entry_replace_new = QLineEdit()
        self.entry_replace_new.setPlaceholderText(tr("mass.new_tag_ph"))
        bulk_layout.addWidget(self.entry_replace_new, 0, 2)

        btn_do_replace = QPushButton(tr("mass.do_replace"))
        btn_do_replace.clicked.connect(self._bulk_replace_tag)
        bulk_layout.addWidget(btn_do_replace, 0, 3)

        # Aggiungi Nuovo Tag
        bulk_layout.addWidget(QLabel(tr("mass.add_tag")), 1, 0)
        self.entry_add_tag = QLineEdit()
        self.entry_add_tag.setPlaceholderText(tr("mass.add_tag_ph"))
        bulk_layout.addWidget(self.entry_add_tag, 1, 1)

        self.combo_add_pos = QComboBox()
        self.combo_add_pos.addItems([tr("mass.pos_append"), tr("mass.pos_prepend")])
        bulk_layout.addWidget(self.combo_add_pos, 1, 2)

        btn_do_add = QPushButton(tr("mass.do_add"))
        btn_do_add.clicked.connect(self._bulk_add_tag)
        bulk_layout.addWidget(btn_do_add, 1, 3)

        # Elimina Tag Selezionati & Pulizia
        btn_delete_selected = QPushButton(tr("mass.delete_checked"))
        btn_delete_selected.setStyleSheet("background-color: #721c24; color: white; font-weight: bold;")
        btn_delete_selected.clicked.connect(self._bulk_delete_checked_tags)
        bulk_layout.addWidget(btn_delete_selected, 2, 0, 1, 2)

        btn_clean_duplicates = QPushButton(tr("mass.clean_dups"))
        btn_clean_duplicates.clicked.connect(self._bulk_clean_duplicates)
        bulk_layout.addWidget(btn_clean_duplicates, 2, 2, 1, 2)


        # Salva Modifiche Massa
        self.btn_save_mass = QPushButton(tr("mass.save_all"))
        self.btn_save_mass.setFixedHeight(36)
        self.btn_save_mass.setStyleSheet("background-color: #0d6efd; color: white; font-size: 13px; font-weight: bold;")
        self.btn_save_mass.clicked.connect(self.save_all_changes_to_disk)
        bulk_layout.addWidget(self.btn_save_mass, 3, 0, 1, 4)

        left_layout.addWidget(bulk_group)
        main_splitter.addWidget(left_panel)


        # --- PANNELLO DESTRO (Galleria Filtrata & Ispettore Immagine) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Galleria Immagini Filtrata
        gallery_group = QGroupBox(tr("mass.gallery_box"))
        gallery_layout = QVBoxLayout(gallery_group)

        self.lbl_gallery_filter_status = QLabel(tr("mass.showing_all"))
        self.lbl_gallery_filter_status.setStyleSheet("color: #00ff66; font-weight: bold; font-size: 11px;")
        gallery_layout.addWidget(self.lbl_gallery_filter_status)

        self.list_gallery_mass = QListWidget()
        self.list_gallery_mass.setIconSize(QSize(64, 64))
        self.list_gallery_mass.itemSelectionChanged.connect(self._on_gallery_selection_changed)
        gallery_layout.addWidget(self.list_gallery_mass)

        right_splitter.addWidget(gallery_group)

        # Ispettore Immagine Selezionata
        inspector_group = QGroupBox(tr("mass.inspector_box"))
        inspector_layout = QHBoxLayout(inspector_group)
        inspector_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_inspector_preview = ZoomableImageView()
        inspector_layout.addWidget(self.lbl_inspector_preview, stretch=2)
        edit_single_layout = QVBoxLayout()
        edit_single_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_single_filename = QLabel(tr("mass.select_photo"))
        self.lbl_single_filename.setStyleSheet("font-weight: bold;")
        edit_single_layout.addWidget(self.lbl_single_filename)

        self.txt_single_tags = QTextEdit()
        self.txt_single_tags.setPlaceholderText(tr("mass.photo_tags_ph"))
        edit_single_layout.addWidget(self.txt_single_tags)

        btn_save_single = QPushButton(tr("mass.save_photo"))
        btn_save_single.clicked.connect(self._save_single_photo_tags)
        edit_single_layout.addWidget(btn_save_single)

        inspector_layout.addLayout(edit_single_layout, stretch=1)
        right_splitter.addWidget(inspector_group)

        right_splitter.setSizes([380, 220])
        right_layout.addWidget(right_splitter)

        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([520, 560])

        layout.addWidget(main_splitter)

    def load_dataset(self, folder_path: str, image_files: List[str], archive_source: str = ""):
        """Carica il dataset nella modalità Mass Edit (le modifiche in memoria vengono scartate)."""
        self.image_folder = folder_path
        self.archive_source = archive_source
        self.checked_tags = set()
        self.dirty = False
        self.image_files = sorted(image_files)
        self.dataset_data = {}
        self.tag_counter = Counter()

        for img_file in self.image_files:
            txt_file = os.path.splitext(img_file)[0] + ".txt"
            txt_path = os.path.join(self.image_folder, txt_file)

            tags = []
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        tags = [t.strip() for t in content.split(",") if t.strip()]
                except Exception as e:
                    self.log_signal.emit(tr("mass.log_read_error", file=txt_file, error=e))

            self.dataset_data[img_file] = tags
            for t in tags:
                self.tag_counter[t] += 1

        total_imgs = len(self.image_files)
        total_unique_tags = len(self.tag_counter)
        total_tag_instances = sum(self.tag_counter.values())

        self.lbl_dataset_stats.setText(
            tr("mass.stats", images=total_imgs, unique=total_unique_tags, total=total_tag_instances)
        )

        self.refresh_tag_table()
        self.refresh_gallery()

    def refresh_tag_table(self):
        """Popola la tabella dei tag con frequenze e percentuali."""
        self.table_tags.blockSignals(True)
        self.table_tags.setSortingEnabled(False)
        self.table_tags.setRowCount(0)

        total_imgs = max(1, len(self.image_files))
        filter_str = self.entry_search_tag.text().strip().lower()

        # Riattiva counter aggiornato
        self.tag_counter = Counter()
        for tags in self.dataset_data.values():
            for t in tags:
                self.tag_counter[t] += 1

        row = 0
        for tag, count in self.tag_counter.most_common():
            if filter_str and filter_str not in tag.lower():
                continue

            self.table_tags.insertRow(row)

            # Colonna 0: Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                              | Qt.ItemFlag.ItemIsSelectable)
            chk_item.setCheckState(Qt.CheckState.Checked if tag in self.checked_tags else Qt.CheckState.Unchecked)
            self.table_tags.setItem(row, 0, chk_item)

            # Colonna 1: Nome Tag
            tag_item = QTableWidgetItem(tag)
            self.table_tags.setItem(row, 1, tag_item)

            # Colonna 2: Conteggio (Numerico per sorting corretto)
            count_item = NumericTableWidgetItem(str(count))
            count_item.setData(Qt.ItemDataRole.UserRole, count)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_tags.setItem(row, 2, count_item)

            # Colonna 3: Copertura Percentuale
            pct = (count / total_imgs) * 100
            pct_item = NumericTableWidgetItem(f"{pct:.1f}%")
            pct_item.setData(Qt.ItemDataRole.UserRole, pct)
            pct_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_tags.setItem(row, 3, pct_item)

            row += 1

        self.table_tags.setSortingEnabled(True)
        self.table_tags.blockSignals(False)
        self.checked_tags &= set(self.tag_counter)

    def _on_tag_item_changed(self, item: QTableWidgetItem):
        if item.column() != 0:
            return
        tag_item = self.table_tags.item(item.row(), 1)
        if tag_item is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self.checked_tags.add(tag_item.text())
        else:
            self.checked_tags.discard(tag_item.text())

    def _checked_tags(self) -> List[str]:
        return [tag for tag, _ in self.tag_counter.most_common() if tag in self.checked_tags]

    def _filter_tag_table(self):
        self.refresh_tag_table()

    def _clear_tag_filter(self):
        self.entry_search_tag.clear()
        self.selected_tag_filter = None
        self.refresh_tag_table()
        self.refresh_gallery()

    def _set_all_checks(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for r in range(self.table_tags.rowCount()):
            item = self.table_tags.item(r, 0)
            if item:
                item.setCheckState(state)

    def _on_tag_table_selection_changed(self):
        selected_rows = self.table_tags.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        tag_item = self.table_tags.item(row, 1)
        if tag_item:
            tag_name = tag_item.text()
            self.selected_tag_filter = tag_name
            self.entry_replace_old.setText(tag_name)
            self.refresh_gallery(filter_tag=tag_name)

    def refresh_gallery(self, filter_tag: Optional[str] = None):
        """Aggiorna la galleria immagini filtrando per il tag selezionato."""
        self.list_gallery_mass.blockSignals(True)
        self.list_gallery_mass.clear()

        if filter_tag is None:
            filter_tag = self.selected_tag_filter

        matching_files = []
        for img_file in self.image_files:
            tags = self.dataset_data.get(img_file, [])
            if filter_tag is None or filter_tag in tags:
                matching_files.append(img_file)

        total_all = len(self.image_files)
        total_matched = len(matching_files)

        if filter_tag:
            self.lbl_gallery_filter_status.setText(
                tr("mass.filtered", tag=filter_tag, matched=total_matched, total=total_all)
            )
        else:
            self.lbl_gallery_filter_status.setText(tr("mass.all_images", total=total_all))

        self.gallery_items = {}
        for img_file in matching_files:
            item = QListWidgetItem(img_file)
            self.gallery_items[img_file] = item
            self.list_gallery_mass.addItem(item)

        self.list_gallery_mass.blockSignals(False)
        self.thumbnails.load((f, os.path.join(self.image_folder, f)) for f in matching_files)

        if self.list_gallery_mass.count() > 0:
            self.list_gallery_mass.setCurrentRow(0)

    def _on_thumbnail_loaded(self, filename: str, image: QImage):
        item = self.gallery_items.get(filename)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    def _on_gallery_selection_changed(self):
        current_item = self.list_gallery_mass.currentItem()
        if not current_item:
            self.lbl_inspector_preview.setText(tr("mass.no_photo"))
            self.lbl_single_filename.setText(tr("mass.select_photo"))
            self.txt_single_tags.setText("")
            return

        filename = current_item.text()
        self.lbl_single_filename.setText(filename)

        img_path = os.path.join(self.image_folder, filename)
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                self.lbl_inspector_preview.setPixmap(pixmap)
            else:
                self.lbl_inspector_preview.setText(tr("mass.photo_read_error"))

        tags = self.dataset_data.get(filename, [])
        self.txt_single_tags.setText(", ".join(tags))

    def _save_single_photo_tags(self):
        current_item = self.list_gallery_mass.currentItem()
        if not current_item:
            return

        filename = current_item.text()
        new_text = self.txt_single_tags.toPlainText().strip()
        new_tags = [t.strip() for t in new_text.split(",") if t.strip()]

        txt_filename = os.path.splitext(filename)[0] + ".txt"
        try:
            self._write_tags(filename, new_tags)
        except OSError as e:
            self.log_signal.emit(tr("mass.log_save_error", file=txt_filename, error=e))
            QMessageBox.critical(self, tr("common.error"), tr("mass.log_save_error", file=txt_filename, error=e))
            return
        self.dataset_data[filename] = new_tags
        self.log_signal.emit(tr("mass.log_photo_saved", file=filename, count=len(new_tags)))
        self.refresh_tag_table()

    def _bulk_replace_tag(self):
        old_tag = self.entry_replace_old.text().strip()
        new_tag_str = self.entry_replace_new.text().strip()

        if not old_tag or not new_tag_str:
            QMessageBox.warning(self, tr("mass.empty_fields_title"), tr("mass.empty_fields_body"))
            return

        new_tags_list = [t.strip() for t in new_tag_str.split(",") if t.strip()]

        replaced_count = 0
        for img_file, tags in self.dataset_data.items():
            if old_tag in tags:
                updated_tags = []
                for t in tags:
                    if t == old_tag:
                        updated_tags.extend(new_tags_list)
                    else:
                        updated_tags.append(t)

                # Deduplicazione mantenendo l'ordine
                seen = set()
                final_tags = []
                for t in updated_tags:
                    if t not in seen:
                        final_tags.append(t)
                        seen.add(t)

                self.dataset_data[img_file] = final_tags
                replaced_count += 1

        self.dirty |= replaced_count > 0
        self.log_signal.emit(tr("mass.log_replaced", old=old_tag, new=new_tag_str, count=replaced_count))
        self.refresh_tag_table()
        self.refresh_gallery()

    def _bulk_add_tag(self):
        add_tag_str = self.entry_add_tag.text().strip()
        if not add_tag_str:
            QMessageBox.warning(self, tr("mass.empty_field_title"), tr("mass.empty_field_body"))
            return

        tags_to_add = [t.strip() for t in add_tag_str.split(",") if t.strip()]
        prepend = (self.combo_add_pos.currentIndex() == 1)

        added_count = 0
        for img_file, tags in self.dataset_data.items():
            # Mantiene l'ordine ed evita duplicati
            existing_set = set(tags)
            new_additions = [t for t in tags_to_add if t not in existing_set]

            if new_additions:
                if prepend:
                    self.dataset_data[img_file] = new_additions + tags
                else:
                    self.dataset_data[img_file] = tags + new_additions
                added_count += 1

        self.dirty |= added_count > 0
        self.log_signal.emit(tr("mass.log_added", tags=add_tag_str, count=added_count))
        self.refresh_tag_table()
        self.refresh_gallery()

    def _bulk_delete_checked_tags(self):
        checked_tags = self._checked_tags()

        if not checked_tags:
            QMessageBox.information(self, tr("mass.none_checked_title"), tr("mass.none_checked_body"))
            return

        confirm = QMessageBox.question(
            self,
            tr("mass.confirm_delete_title"),
            tr("mass.confirm_delete_body", count=len(checked_tags)) + "\n\n" + ", ".join(checked_tags[:10]) + ("..." if len(checked_tags) > 10 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        delete_set = set(checked_tags)
        modified_files = 0

        for img_file, tags in self.dataset_data.items():
            new_tags = [t for t in tags if t not in delete_set]
            if len(new_tags) != len(tags):
                self.dataset_data[img_file] = new_tags
                modified_files += 1

        self.dirty |= modified_files > 0
        self.log_signal.emit(tr("mass.log_deleted", count=len(checked_tags), files=modified_files))
        self.refresh_tag_table()
        self.refresh_gallery()

    def _bulk_clean_duplicates(self):
        cleaned_files = 0
        for img_file, tags in self.dataset_data.items():
            seen = set()
            new_tags = []
            for t in tags:
                t_clean = t.strip()
                if t_clean and t_clean not in seen:
                    new_tags.append(t_clean)
                    seen.add(t_clean)

            if len(new_tags) != len(tags):
                self.dataset_data[img_file] = new_tags
                cleaned_files += 1

        self.dirty |= cleaned_files > 0
        self.log_signal.emit(tr("mass.log_cleaned", files=cleaned_files))
        self.refresh_tag_table()
        self.refresh_gallery()

    def _write_tags(self, img_file: str, tags: List[str]):
        txt_path = os.path.join(self.image_folder, os.path.splitext(img_file)[0] + ".txt")
        layout.write_text_atomic(txt_path, ", ".join(tags))

    def save_all_changes_to_disk(self, quiet: bool = False) -> bool:
        """Scrive permanentemente le modifiche dei tag sui file .txt su disco. True se tutto è stato salvato."""
        if not self.image_folder or not os.path.exists(self.image_folder):
            QMessageBox.warning(self, tr("mass.no_dataset_title"), tr("mass.no_dataset_body"))
            return False

        written_count = 0
        errors = 0
        for img_file, tags in self.dataset_data.items():
            try:
                self._write_tags(img_file, tags)
                written_count += 1
            except OSError as e:
                errors += 1
                self.log_signal.emit(tr("mass.log_save_error", file=os.path.splitext(img_file)[0] + ".txt", error=e))

        self.log_signal.emit(tr("mass.log_saved_all", count=written_count))
        if errors:
            return False
        self.dirty = False
        # Un archivio estratto vive in una cartella temporanea: va riesportato o le modifiche si perdono
        if self.archive_source:
            self._export_archive()
        if not quiet:
            QMessageBox.information(self, tr("mass.saved_title"), tr("mass.saved_body", count=written_count))
        self.dataset_updated_signal.emit()
        return True

    def _export_archive(self):
        default_path = os.path.join(os.path.dirname(self.archive_source),
                                    archive_stem(self.archive_source) + "_edited.zip")
        path, _ = QFileDialog.getSaveFileName(self, tr("mass.export_title"), default_path, "ZIP (*.zip)")
        if not path:
            self.log_signal.emit(tr("mass.log_export_skipped", path=self.image_folder))
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            write_zip(self.image_folder, path)
        except OSError as e:
            QMessageBox.critical(self, tr("source.archive_error_title"), tr("common.archive_error", error=e))
            return
        self.log_signal.emit(tr("mass.log_exported", path=path))

    def maybe_save(self, allow_cancel: bool = True) -> bool:
        """Chiede cosa fare delle modifiche non salvate. False se l'utente annulla (o il salvataggio fallisce)."""
        if not self.dirty:
            return True
        buttons = QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
        if allow_cancel:
            buttons |= QMessageBox.StandardButton.Cancel
        answer = QMessageBox.question(self, tr("mass.unsaved_title"), tr("mass.unsaved_body"), buttons,
                                      QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_all_changes_to_disk(quiet=True) or not allow_cancel
        if answer == QMessageBox.StandardButton.Discard:
            self.dirty = False
            self.log_signal.emit(tr("mass.log_discarded"))
            return True
        return False

    def _on_click_load_folder(self):
        if not self.maybe_save():
            return
        folder = QFileDialog.getExistingDirectory(self, tr("mass.pick_folder"))
        if not folder:
            return

        jpg_files = [f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]
        if not jpg_files:
            QMessageBox.warning(self, tr("common.no_images_title"), tr("source.no_images_folder"))
            return

        self.load_dataset(folder, jpg_files)
        self.log_signal.emit(tr("mass.log_folder", path=folder, count=len(jpg_files)))

    def _on_click_load_archive(self):
        if not self.maybe_save():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, tr("source.pick_archive"), "", archive_filter())
        if not file_path:
            return

        try:
            extracted_imgs = extract_archive(file_path, MASS_EDIT_TEMP_DIR)
        except Exception as e:
            QMessageBox.critical(self, tr("source.archive_error_title"), tr("source.archive_error_body", error=e))
            return
        if extracted_imgs:
            self.load_dataset(MASS_EDIT_TEMP_DIR, extracted_imgs, archive_source=file_path)
            self.log_signal.emit(tr("mass.log_archive", name=os.path.basename(file_path), count=len(extracted_imgs)))
        else:
            QMessageBox.warning(self, tr("mass.empty_archive_title"), tr("source.no_images_archive"))
