"""Execucao segura do chdman.exe.

O conversor roda fora da thread da interface e comunica progresso por callbacks.
Ele valida o resultado olhando o codigo de saida e a existencia real do arquivo
.chd gerado.
"""

from pathlib import Path
import queue
import subprocess
import threading
import time

from app.utils import resolve_cue_bin_map


def _extract_percent(text):
    """Tenta extrair o ultimo percentual presente em um trecho de saida."""
    percent_index = text.rfind("%")
    if percent_index < 0:
        return None

    start = percent_index - 1
    while start >= 0 and (text[start].isdigit() or text[start] == "."):
        start -= 1

    number = text[start + 1:percent_index]
    if not number:
        return None

    try:
        value = int(float(number))
    except ValueError:
        return None

    if value < 0:
        return 0
    if value > 100:
        return 100
    return value


def _cue_text_with_existing_bins(cue_path):
    """Retorna texto do CUE apontando para BINs reais quando houver renomeio."""
    mapping = resolve_cue_bin_map(cue_path)
    if not mapping:
        return None

    try:
        text = cue_path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return None

    changed = False
    for referenced_name, bin_path in mapping:
        if referenced_name == bin_path.name:
            continue
        text = text.replace(f'"{referenced_name}"', f'"{bin_path.name}"')
        text = text.replace(f" {referenced_name} ", f" {bin_path.name} ")
        changed = True

    return text if changed else None


def convert_to_chd(cue_file, chdman_file, chd_file, cancel_event, progress_callback, log_callback):
    """Converte um CUE para CHD usando chdman.exe createcd."""
    cue_path = Path(cue_file)
    chd_path = Path(chd_file)
    chdman_path = Path(chdman_file)
    input_cue_path = cue_path
    temp_cue_path = None
    start_time = time.perf_counter()
    return_code = None

    def metrics(success, message):
        elapsed = time.perf_counter() - start_time
        chd_size = 0
        try:
            if chd_path.exists():
                chd_size = chd_path.stat().st_size
        except OSError:
            chd_size = 0
        return {
            "success": bool(success),
            "message": message,
            "elapsed_seconds": elapsed,
            "chd_size": chd_size,
            "return_code": return_code,
        }

    if not cue_path.exists():
        message = "Arquivo CUE nao encontrado."
        return False, message, metrics(False, message)
    if not chdman_path.exists():
        message = "chdman.exe nao encontrado."
        return False, message, metrics(False, message)

    try:
        chd_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = f"Nao foi possivel criar a pasta destino: {exc}"
        return False, message, metrics(False, message)

    fixed_cue_text = _cue_text_with_existing_bins(cue_path)
    if fixed_cue_text:
        temp_cue_path = cue_path.with_name(f".__chd_converter_{cue_path.name}")
        temp_cue_path.write_text(fixed_cue_text, encoding="utf-8")
        input_cue_path = temp_cue_path
        log_callback("CUE temporario criado com nomes de BIN ajustados.")

    command = [
        str(chdman_path),
        "createcd",
        "-i",
        str(input_cue_path),
        "-o",
        str(chd_path),
    ]

    log_callback(f"Iniciando: {cue_path}")
    log_callback(f"Destino CHD: {chd_path}")
    process = None
    output_buffer = ""
    last_percent = -1

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cue_path.parent),
        )

        output_queue = queue.Queue()

        def reader():
            """Le a saida do processo sem bloquear o controle de cancelamento."""
            try:
                while True:
                    data = process.stdout.read(1) if process.stdout else ""
                    if not data:
                        break
                    output_queue.put(data)
            except OSError:
                pass
            finally:
                output_queue.put(None)

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        # chdman costuma atualizar progresso com retornos de carro. Ler em
        # blocos pequenos permite refletir progresso sem esperar uma linha nova.
        reader_done = False
        while True:
            if cancel_event.is_set():
                process.terminate()
                message = "Conversao cancelada pelo usuario."
                return False, message, metrics(False, message)

            try:
                chunk = output_queue.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is not None and reader_done:
                    break
                continue

            if chunk is None:
                reader_done = True
                if process.poll() is not None:
                    break
                continue

            if chunk:
                output_buffer += chunk
                if chunk in ("\n", "\r"):
                    cleaned = output_buffer.strip()
                    if cleaned:
                        log_callback(cleaned)
                    output_buffer = ""
                else:
                    percent = _extract_percent(output_buffer)
                    if percent is not None and percent != last_percent:
                        last_percent = percent
                        progress_callback(percent)
                continue

        cleaned_tail = output_buffer.strip()
        if cleaned_tail:
            log_callback(cleaned_tail)

        return_code = process.wait()
        if return_code == 0 and chd_path.exists() and chd_path.stat().st_size > 0:
            progress_callback(100)
            message = "Conversao concluida com sucesso."
            return True, message, metrics(True, message)

        if chd_path.exists() and chd_path.stat().st_size == 0:
            try:
                chd_path.unlink()
            except OSError:
                pass
        message = f"chdman finalizou com codigo {return_code}."
        return False, message, metrics(False, message)

    except FileNotFoundError:
        message = "Nao foi possivel executar o chdman.exe."
        return False, message, metrics(False, message)
    except OSError as exc:
        message = f"Falha do sistema ao converter: {exc}"
        return False, message, metrics(False, message)
    finally:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        if temp_cue_path and temp_cue_path.exists():
            try:
                temp_cue_path.unlink()
            except OSError:
                pass
