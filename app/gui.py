"""Interface grafica principal do CHD Batch Converter."""

from pathlib import Path
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.styles import APP_STYLE
from app.utils import (
    APP_NAME,
    STATUS_CONVERTING,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_EXISTS,
    STATUS_READY,
    WINDOW_TITLE,
    default_output_path,
    find_chdman,
    load_settings,
    save_settings,
)
from app.worker import ConversionQueue, ScanWorker, WorkerSignals


class MainWindow(QMainWindow):
    """Janela principal com tabela, controles, logs e fila de conversao."""

    COL_SELECT = 0
    COL_NAME = 1
    COL_PATH = 2
    COL_SIZE = 3
    COL_STATUS = 4
    COL_PROGRESS = 5
    COL_ACTION = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1280, 780)
        self.setMinimumSize(980, 620)
        self.setStyleSheet(APP_STYLE)

        self.settings = load_settings()
        self.records = {}
        self.scan_worker = None
        self.signals = WorkerSignals()
        self.conversion_queue = ConversionQueue(
            self.signals,
            max_parallel=int(self.settings.get("parallel_jobs", "2") or "2"),
        )

        found_chdman = find_chdman()
        self.chdman_path = str(found_chdman) if found_chdman else self.settings.get("chdman_path", "")
        self.output_folder = self.settings.get("output_folder") or str(default_output_path())
        self.current_folder = self.settings.get("last_folder", "")

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._update_chdman_label()
        self._update_output_label()

        QTimer.singleShot(250, self._warn_if_chdman_missing)

    def _build_actions(self):
        """Cria o menu superior simples."""
        menu_file = self.menuBar().addMenu("Arquivo")

        select_folder = QAction("Selecionar Pasta", self)
        select_folder.triggered.connect(self.select_folder)
        menu_file.addAction(select_folder)

        select_chdman = QAction("Selecionar chdman.exe", self)
        select_chdman.triggered.connect(self.select_chdman)
        menu_file.addAction(select_chdman)

        select_output = QAction("Selecionar pasta destino", self)
        select_output.triggered.connect(self.select_output_folder)
        menu_file.addAction(select_output)

        menu_file.addSeparator()
        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self.close)
        menu_file.addAction(exit_action)

        menu_selection = self.menuBar().addMenu("Selecao")
        select_all = QAction("Marcar todos", self)
        select_all.triggered.connect(lambda: self._set_all_checked(True))
        menu_selection.addAction(select_all)

        clear_selection = QAction("Desmarcar todos", self)
        clear_selection.triggered.connect(lambda: self._set_all_checked(False))
        menu_selection.addAction(clear_selection)

    def _build_ui(self):
        """Monta a interface em barra superior, tabela central e painel inferior."""
        root = QWidget()
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        top_layout.addWidget(title)

        self.folder_label = QLabel("Nenhuma pasta selecionada")
        self.folder_label.setObjectName("mutedLabel")
        top_layout.addWidget(self.folder_label, 1)

        self.chdman_label = QLabel()
        self.chdman_label.setObjectName("mutedLabel")
        top_layout.addWidget(self.chdman_label)

        self.output_label = QLabel()
        self.output_label.setObjectName("mutedLabel")
        top_layout.addWidget(self.output_label)

        self.select_folder_button = QPushButton("Selecionar Pasta")
        self.select_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.select_folder_button.clicked.connect(self.select_folder)
        top_layout.addWidget(self.select_folder_button)

        self.select_chdman_button = QPushButton("chdman.exe")
        self.select_chdman_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.select_chdman_button.clicked.connect(self.select_chdman)
        top_layout.addWidget(self.select_chdman_button)

        self.select_output_button = QPushButton("Destino")
        self.select_output_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.select_output_button.clicked.connect(self.select_output_folder)
        top_layout.addWidget(self.select_output_button)

        main_layout.addWidget(top_bar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(10)

        controls_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrar por nome ou caminho")
        self.search_edit.textChanged.connect(self.apply_filter)
        controls_layout.addWidget(self.search_edit, 1)

        controls_layout.addWidget(QLabel("Conversoes paralelas"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 4)
        self.parallel_spin.setValue(int(self.settings.get("parallel_jobs", "2") or "2"))
        self.parallel_spin.valueChanged.connect(self._save_parallel_setting)
        controls_layout.addWidget(self.parallel_spin)

        self.convert_selected_button = QPushButton("Converter Selecionados")
        self.convert_selected_button.setObjectName("primaryButton")
        self.convert_selected_button.clicked.connect(self.convert_selected)
        controls_layout.addWidget(self.convert_selected_button)

        self.convert_all_button = QPushButton("Converter Todos")
        self.convert_all_button.clicked.connect(self.convert_all)
        controls_layout.addWidget(self.convert_all_button)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self.cancel_conversions)
        self.cancel_button.setEnabled(False)
        controls_layout.addWidget(self.cancel_button)
        content_layout.addLayout(controls_layout)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Selecao",
            "Nome do jogo",
            "Caminho",
            "Tamanho",
            "Status",
            "Progresso",
            "Acao",
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_SELECT, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_PATH, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_PROGRESS, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_ACTION, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._table_item_changed)
        content_layout.addWidget(self.table, 1)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        progress_layout = QHBoxLayout()
        self.overall_progress = QProgressBar()
        self.overall_progress.setValue(0)
        progress_layout.addWidget(self.overall_progress, 1)
        self.counter_label = QLabel("0 jogos encontrados")
        self.counter_label.setObjectName("mutedLabel")
        progress_layout.addWidget(self.counter_label)
        bottom_layout.addLayout(progress_layout)

        self.log_panel = QPlainTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumBlockCount(1200)
        self.log_panel.setPlaceholderText("Logs de varredura e conversao")
        bottom_layout.addWidget(self.log_panel)
        content_layout.addWidget(bottom)

        main_layout.addWidget(content, 1)

        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(16, 7, 16, 7)
        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("mutedLabel")
        status_layout.addWidget(self.status_label)
        main_layout.addWidget(status_bar)

        self.setCentralWidget(root)

    def _connect_signals(self):
        """Liga sinais dos workers aos slots da GUI."""
        self.signals.log.connect(self.add_log)
        self.signals.scan_started.connect(self._on_scan_started)
        self.signals.game_found.connect(self._add_game_row)
        self.signals.scan_finished.connect(self._on_scan_finished)
        self.signals.conversion_started.connect(self._on_conversion_started)
        self.signals.conversion_progress.connect(self._on_conversion_progress)
        self.signals.conversion_finished.connect(self._on_conversion_finished)
        self.signals.batch_progress.connect(self._on_batch_progress)
        self.signals.queue_finished.connect(self._on_queue_finished)

    def select_folder(self):
        """Abre seletor de pasta e inicia varredura automaticamente."""
        start_dir = self.settings.get("last_folder") or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta de jogos", start_dir)
        if not folder:
            return

        self.settings["last_folder"] = folder
        self.current_folder = folder
        save_settings(self.settings)
        self.folder_label.setText(folder)
        self.start_scan(folder)

    def select_chdman(self):
        """Permite informar manualmente o executavel chdman.exe."""
        start_dir = str(Path(self.chdman_path).parent) if self.chdman_path else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecionar chdman.exe", start_dir, "chdman.exe (chdman.exe)")
        if not file_path:
            return

        if Path(file_path).name.lower() != "chdman.exe":
            QMessageBox.warning(self, "Arquivo invalido", "Selecione o arquivo chdman.exe.")
            return

        self.chdman_path = file_path
        self.settings["chdman_path"] = file_path
        save_settings(self.settings)
        self._update_chdman_label()
        self.add_log(f"chdman configurado: {file_path}")

    def select_output_folder(self):
        """Permite escolher onde os arquivos CHD serao salvos."""
        start_dir = self.output_folder or str(default_output_path())
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta destino dos CHDs", start_dir)
        if not folder:
            return

        self.output_folder = folder
        self.settings["output_folder"] = folder
        save_settings(self.settings)
        self._update_output_label()
        self.add_log(f"Pasta destino configurada: {folder}")
        if self.current_folder:
            self.start_scan(self.current_folder)

    def start_scan(self, folder):
        """Limpa resultados atuais e inicia uma nova varredura."""
        if self.scan_worker and self.scan_worker.is_alive():
            self.scan_worker.cancel()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self.records.clear()
        self.overall_progress.setValue(0)
        self.counter_label.setText("0 jogos encontrados")
        self.status_label.setText("Varredura em andamento")

        self.scan_worker = ScanWorker(folder, self.output_folder, self.signals)
        self.scan_worker.start()

    def convert_selected(self):
        """Converte apenas jogos marcados na tabela."""
        records = []
        for record in self.records.values():
            if record.get("selected") and record.get("status") != STATUS_EXISTS:
                records.append(record)
        self._start_conversion(records)

    def convert_all(self):
        """Converte todos os jogos elegiveis encontrados."""
        records = []
        for record in self.records.values():
            if record.get("status") != STATUS_EXISTS:
                records.append(record)
        self._start_conversion(records)

    def convert_single(self, record_id):
        """Converte um unico jogo a partir do botao da linha."""
        record = self.records.get(record_id)
        if record:
            self._start_conversion([record])

    def cancel_conversions(self):
        """Cancela conversoes ativas."""
        self.conversion_queue.cancel()
        self.cancel_button.setEnabled(False)

    def apply_filter(self):
        """Filtra linhas por nome ou caminho sem alterar os dados."""
        text = self.search_edit.text().strip().lower()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, self.COL_NAME).text().lower()
            path = self.table.item(row, self.COL_PATH).text().lower()
            self.table.setRowHidden(row, text not in name and text not in path)

    def add_log(self, message):
        """Adiciona uma linha ao painel de logs."""
        self.log_panel.appendPlainText(message)

    def _start_conversion(self, records):
        """Valida chdman e entrega itens para a fila paralela."""
        if not self._has_valid_chdman():
            QMessageBox.information(
                self,
                "chdman.exe necessario",
                "Coloque o chdman.exe na pasta do aplicativo ou selecione o executavel manualmente.",
            )
            return

        self.conversion_queue.max_parallel = self.parallel_spin.value()
        started = self.conversion_queue.start(records, self.chdman_path)
        if started:
            self.cancel_button.setEnabled(True)
            self.convert_all_button.setEnabled(False)
            self.convert_selected_button.setEnabled(False)
            self.status_label.setText("Conversao em andamento")

    def _add_game_row(self, record):
        """Insere um jogo encontrado na tabela."""
        self.records[record["id"]] = record
        self.table.setSortingEnabled(False)
        row = self.table.rowCount()
        self.table.insertRow(row)

        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Checked if record["selected"] else Qt.CheckState.Unchecked)
        check_item.setData(Qt.ItemDataRole.UserRole, record["id"])
        self.table.setItem(row, self.COL_SELECT, check_item)

        name_item = QTableWidgetItem(record["name"])
        name_item.setData(Qt.ItemDataRole.UserRole, record["id"])
        self.table.setItem(row, self.COL_NAME, name_item)
        self.table.setItem(row, self.COL_PATH, QTableWidgetItem(record["path"]))
        self.table.setItem(row, self.COL_SIZE, QTableWidgetItem(record["size_text"]))
        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(record["status"]))

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(record["progress"])
        self.table.setCellWidget(row, self.COL_PROGRESS, progress)

        button = QPushButton("Converter")
        button.setEnabled(record["status"] != STATUS_EXISTS)
        button.clicked.connect(lambda checked=False, rid=record["id"]: self.convert_single(rid))
        self.table.setCellWidget(row, self.COL_ACTION, button)

        self.table.setSortingEnabled(True)
        self.counter_label.setText(f"{len(self.records)} jogos encontrados")
        self.apply_filter()

    def _find_row(self, record_id):
        """Encontra a linha atual de um registro mesmo apos ordenacao."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_NAME)
            if item and item.data(Qt.ItemDataRole.UserRole) == record_id:
                return row
        return -1

    def _set_status(self, record_id, status):
        """Atualiza status em memoria e na tabela."""
        record = self.records.get(record_id)
        if record:
            record["status"] = status
        row = self._find_row(record_id)
        if row >= 0:
            self.table.item(row, self.COL_STATUS).setText(status)

    def _set_progress(self, record_id, value):
        """Atualiza progresso individual."""
        record = self.records.get(record_id)
        if record:
            record["progress"] = value
        row = self._find_row(record_id)
        if row >= 0:
            progress = self.table.cellWidget(row, self.COL_PROGRESS)
            if progress:
                progress.setValue(value)

    def _set_action_enabled(self, record_id, enabled):
        """Ativa ou desativa o botao Converter de uma linha."""
        row = self._find_row(record_id)
        if row >= 0:
            button = self.table.cellWidget(row, self.COL_ACTION)
            if button:
                button.setEnabled(enabled)

    def _table_item_changed(self, item):
        """Sincroniza checkbox da tabela com o registro em memoria."""
        if item.column() != self.COL_SELECT:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)
        record = self.records.get(record_id)
        if record:
            record["selected"] = item.checkState() == Qt.CheckState.Checked

    def _set_all_checked(self, checked):
        """Marca ou desmarca todos os jogos visiveis e elegiveis."""
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            item = self.table.item(row, self.COL_SELECT)
            record_id = item.data(Qt.ItemDataRole.UserRole)
            record = self.records.get(record_id)
            if record and record.get("status") != STATUS_EXISTS:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _on_scan_started(self, folder):
        self.add_log(f"Procurando jogos em: {folder}")
        self.status_label.setText("Varredura em andamento")

    def _on_scan_finished(self, records):
        self.table.setSortingEnabled(True)
        self.counter_label.setText(f"{len(records)} jogos encontrados")
        self.status_label.setText("Varredura finalizada")

    def _on_conversion_started(self, record_id):
        self._set_status(record_id, STATUS_CONVERTING)
        self._set_progress(record_id, 0)
        self._set_action_enabled(record_id, False)

    def _on_conversion_progress(self, record_id, value):
        self._set_progress(record_id, value)

    def _on_conversion_finished(self, record_id, success, message):
        self._set_status(record_id, STATUS_DONE if success else STATUS_ERROR)
        if success:
            self._set_progress(record_id, 100)
        self._set_action_enabled(record_id, not success)
        self.add_log(message)

    def _on_batch_progress(self, done, total):
        if total <= 0:
            self.overall_progress.setValue(0)
            self.overall_progress.setFormat("0 / 0 - 0%")
            return
        percent = int((done / total) * 100)
        self.overall_progress.setValue(percent)
        self.overall_progress.setFormat(f"{done} / {total} - {percent}%")

    def _on_queue_finished(self):
        self.cancel_button.setEnabled(False)
        self.convert_all_button.setEnabled(True)
        self.convert_selected_button.setEnabled(True)
        self.status_label.setText("Conversao finalizada")
        self.add_log("Fila de conversao finalizada.")

    def _save_parallel_setting(self, value):
        self.settings["parallel_jobs"] = str(value)
        save_settings(self.settings)

    def _has_valid_chdman(self):
        return bool(self.chdman_path and Path(self.chdman_path).exists())

    def _update_chdman_label(self):
        if self._has_valid_chdman():
            self.chdman_label.setText(f"chdman: {os.path.basename(self.chdman_path)}")
        else:
            self.chdman_label.setText("chdman nao configurado")

    def _update_output_label(self):
        self.output_label.setText(f"destino: {os.path.basename(self.output_folder) or self.output_folder}")

    def _warn_if_chdman_missing(self):
        if self._has_valid_chdman():
            return
        self.add_log("chdman.exe nao encontrado na pasta do aplicativo.")
        QMessageBox.information(
            self,
            "chdman.exe nao encontrado",
            "O chdman.exe nao foi encontrado na pasta do aplicativo. Voce pode seleciona-lo manualmente pelo botao chdman.exe.",
        )

    def closeEvent(self, event):
        """Cancela tarefas em andamento antes de fechar."""
        if self.conversion_queue.running:
            self.conversion_queue.cancel()
        if self.scan_worker and self.scan_worker.is_alive():
            self.scan_worker.cancel()
        event.accept()
