"""Workers de varredura e conversao.

As classes deste modulo usam threading.Thread para manter a interface
responsiva mesmo com centenas de jogos e conversoes longas.
"""

from pathlib import Path
import csv
import datetime as dt
import queue
import threading

from PySide6.QtCore import QObject, Signal

from app.converter import convert_to_chd
from app.utils import (
    STATUS_CONVERTING,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_EXISTS,
    build_game_record,
    create_missing_cues,
    validate_cue_with_bins,
)


class WorkerSignals(QObject):
    """Ponte Qt segura para emitir eventos a partir de threads Python."""

    log = Signal(str)
    scan_started = Signal(str)
    game_found = Signal(object)
    scan_finished = Signal(object)
    conversion_started = Signal(str)
    conversion_progress = Signal(str, int)
    conversion_finished = Signal(str, bool, str)
    batch_progress = Signal(int, int)
    queue_finished = Signal()


class ScanWorker(threading.Thread):
    """Procura arquivos .cue validos de forma recursiva."""

    def __init__(self, folder, output_folder, signals):
        super().__init__(daemon=True)
        self.folder = Path(folder)
        self.output_folder = Path(output_folder)
        self.signals = signals
        self._cancel = threading.Event()

    def cancel(self):
        """Solicita cancelamento da varredura."""
        self._cancel.set()

    def run(self):
        """Executa a varredura e emite um registro por jogo valido."""
        records = []
        seen = set()
        self.signals.scan_started.emit(str(self.folder))
        self.signals.log.emit(f"Varredura iniciada em: {self.folder}")
        self.signals.log.emit(f"Pasta destino dos CHDs: {self.output_folder}")

        try:
            created_cues = create_missing_cues(self.folder)
            for cue_path in created_cues:
                if self._cancel.is_set():
                    self.signals.log.emit("Criacao de CUEs cancelada.")
                    break
                self.signals.log.emit(f"CUE criado para BIN sem CUE: {cue_path}")

            iterator = self.folder.rglob("*.cue")
            for cue_path in iterator:
                if self._cancel.is_set():
                    self.signals.log.emit("Varredura cancelada.")
                    break

                key = str(cue_path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)

                bins = validate_cue_with_bins(cue_path)
                if not bins:
                    self.signals.log.emit(f"Ignorado sem BIN correspondente: {cue_path}")
                    continue

                record = build_game_record(cue_path, bins, self.output_folder)
                records.append(record)
                self.signals.game_found.emit(record)
                self.signals.log.emit(f"Encontrado: {cue_path}")
        except OSError as exc:
            self.signals.log.emit(f"Erro durante a varredura: {exc}")

        self.signals.scan_finished.emit(records)
        self.signals.log.emit(f"Varredura finalizada. Jogos validos: {len(records)}")


class ConversionQueue:
    """Fila de conversao com paralelismo limitado e cancelamento global."""

    def __init__(self, signals, max_parallel=2):
        self.signals = signals
        self.max_parallel = max(1, int(max_parallel))
        self.cancel_event = threading.Event()
        self.work_queue = queue.Queue()
        self.lock = threading.Lock()
        self.metrics_lock = threading.Lock()
        self.active_ids = set()
        self.total = 0
        self.done = 0
        self.running = False
        self.threads = []
        self.remaining_threads = 0
        self.metrics_path = None

    def start(self, records, chdman_path):
        """Inicia a fila, ignorando itens duplicados ou ja em execucao."""
        if self.running:
            self.signals.log.emit("Ja existe uma conversao em andamento.")
            return False

        self.cancel_event.clear()
        self.work_queue = queue.Queue()
        self.done = 0
        self.total = 0
        self.threads = []
        queued = set()

        for record in records:
            record_id = record["id"]
            if record_id in queued or record_id in self.active_ids:
                continue
            if record.get("status") == STATUS_EXISTS:
                continue
            queued.add(record_id)
            self.work_queue.put(record)
            self.total += 1

        if self.total == 0:
            self.signals.log.emit("Nenhum jogo elegivel para conversao.")
            self.signals.batch_progress.emit(0, 0)
            return False

        self.running = True
        first_record = records[0]
        self.metrics_path = Path(first_record["chd_path"]).parent / "conversion_metrics.csv"
        self.signals.batch_progress.emit(0, self.total)
        workers = min(self.max_parallel, self.total)
        self.remaining_threads = workers
        for index in range(workers):
            thread = threading.Thread(
                target=self._worker_loop,
                args=(str(chdman_path), index + 1),
                daemon=True,
            )
            self.threads.append(thread)
            thread.start()
        return True

    def cancel(self):
        """Solicita cancelamento das conversoes ativas e pendentes."""
        self.cancel_event.set()
        self.signals.log.emit("Cancelamento solicitado. Aguardando processos pararem.")

    def _worker_loop(self, chdman_path, worker_number):
        """Consome a fila ate esvaziar ou ate o usuario cancelar."""
        self.signals.log.emit(f"Worker {worker_number} iniciado.")
        while not self.cancel_event.is_set():
            try:
                record = self.work_queue.get_nowait()
            except queue.Empty:
                break

            record_id = record["id"]
            with self.lock:
                self.active_ids.add(record_id)

            cue_path = record["path"]
            self.signals.conversion_started.emit(record_id)
            self.signals.log.emit(f"Convertendo: {cue_path}")

            def progress_callback(value):
                self.signals.conversion_progress.emit(record_id, int(value))

            def log_callback(message):
                if message:
                    self.signals.log.emit(message)

            success, message, metrics = convert_to_chd(
                cue_path,
                chdman_path,
                record["chd_path"],
                self.cancel_event,
                progress_callback,
                log_callback,
            )
            self._write_metrics(record, metrics, worker_number)

            with self.lock:
                self.active_ids.discard(record_id)
                self.done += 1
                done = self.done
                total = self.total

            self.signals.conversion_finished.emit(record_id, success, message)
            self.signals.batch_progress.emit(done, total)
            self.work_queue.task_done()

        self.signals.log.emit(f"Worker {worker_number} finalizado.")
        self._maybe_finish()

    def _write_metrics(self, record, metrics, worker_number):
        """Acrescenta uma linha de metricas da conversao em CSV."""
        if not self.metrics_path:
            return

        source_size = int(record.get("size", 0) or 0)
        chd_size = int(metrics.get("chd_size", 0) or 0)
        elapsed = float(metrics.get("elapsed_seconds", 0) or 0)
        compression_percent = (chd_size / source_size * 100) if source_size else 0
        saved_bytes = source_size - chd_size if chd_size else 0
        throughput_mbps = (source_size / 1024 / 1024 / elapsed) if elapsed > 0 else 0

        row = {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "worker": worker_number,
            "game": record.get("name", ""),
            "cue_path": record.get("path", ""),
            "chd_path": record.get("chd_path", ""),
            "success": metrics.get("success", False),
            "return_code": metrics.get("return_code", ""),
            "source_size_bytes": source_size,
            "chd_size_bytes": chd_size,
            "saved_bytes": saved_bytes,
            "compression_percent": f"{compression_percent:.2f}",
            "elapsed_seconds": f"{elapsed:.3f}",
            "throughput_mb_s": f"{throughput_mbps:.2f}",
            "message": metrics.get("message", ""),
        }
        fieldnames = list(row.keys())

        with self.metrics_lock:
            try:
                self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
                write_header = not self.metrics_path.exists() or self.metrics_path.stat().st_size == 0
                with self.metrics_path.open("a", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow(row)
            except OSError as exc:
                self.signals.log.emit(f"Nao foi possivel salvar metricas: {exc}")

    def _maybe_finish(self):
        """Emite finalizacao quando todas as threads terminaram."""
        with self.lock:
            self.remaining_threads -= 1
            if self.remaining_threads > 0:
                return
            self.running = False
        self.signals.queue_finished.emit()
