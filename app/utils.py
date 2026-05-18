"""Funcoes utilitarias do CHD Batch Converter.

Este modulo concentra tarefas pequenas e reutilizaveis para manter a GUI e os
workers mais simples: formatacao de tamanho, descoberta do chdman.exe,
validacao de CUE/BIN e persistencia leve das ultimas pastas usadas.
"""

from pathlib import Path
import os
import sys


APP_NAME = "CHD Batch Converter"
WINDOW_TITLE = "CHD Batch Converter - BIN/CUE para CHD"
DEFAULT_OUTPUT_DIR_NAME = "Games_CHDs"
STATUS_READY = "Pronto"
STATUS_CONVERTING = "Convertendo"
STATUS_DONE = "Concluido"
STATUS_ERROR = "Erro"
STATUS_EXISTS = "CHD ja existe"


def app_base_path():
    """Retorna a pasta base do aplicativo, funcionando no Python e PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_output_path():
    """Retorna a pasta padrao de destino dos CHDs."""
    return app_base_path() / DEFAULT_OUTPUT_DIR_NAME


def config_path():
    """Retorna o arquivo simples usado para salvar as ultimas escolhas."""
    root = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.txt"


def load_settings():
    """Carrega configuracoes salvas em formato chave=valor, sem dependencias extras."""
    settings = {
        "last_folder": "",
        "chdman_path": "",
        "parallel_jobs": "2",
        "output_folder": str(default_output_path()),
    }
    path = config_path()
    if not path.exists():
        return settings

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key in settings:
                    settings[key] = value
    except OSError:
        pass
    return settings


def save_settings(settings):
    """Salva configuracoes em disco de modo tolerante a falhas."""
    lines = []
    for key in ("last_folder", "chdman_path", "parallel_jobs", "output_folder"):
        lines.append(f"{key}={settings.get(key, '')}")
    try:
        config_path().write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


def find_chdman():
    """Procura chdman.exe na pasta do aplicativo e retorna Path ou None."""
    candidates = [
        app_base_path() / "chdman.exe",
        Path(__file__).resolve().parent / "chdman.exe",
        Path.cwd() / "chdman.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.name.lower() == "chdman.exe":
            return candidate
    return None


def format_size(size_bytes):
    """Formata bytes em texto amigavel para a tabela."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size = size / 1024
    return f"{size_bytes} B"


def case_insensitive_child(parent, file_name):
    """Localiza um arquivo na pasta ignorando diferencas de maiusculas/minusculas."""
    direct = parent / file_name
    if direct.exists():
        return direct

    wanted = file_name.lower()
    try:
        for child in parent.iterdir():
            if child.name.lower() == wanted:
                return child
    except OSError:
        return direct
    return direct


def cue_referenced_files(cue_path):
    """Extrai os arquivos FILE de um .cue sem usar parser externo."""
    files = []
    try:
        lines = cue_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return files

    for raw_line in lines:
        line = raw_line.strip().lstrip("\ufeff")
        if not line.upper().startswith("FILE "):
            continue

        # O formato comum e: FILE "nome do disco.bin" BINARY.
        first_quote = line.find('"')
        second_quote = line.find('"', first_quote + 1)
        if first_quote >= 0 and second_quote > first_quote:
            name = line[first_quote + 1:second_quote]
        else:
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1]

        if name:
            files.append(name)
    return files


def folder_bin_files(folder):
    """Lista BINs da pasta em ordem estavel."""
    try:
        return sorted(
            (child for child in folder.iterdir() if child.is_file() and child.suffix.lower() == ".bin"),
            key=lambda item: item.name.lower(),
        )
    except OSError:
        return []


def resolve_cue_bin_map(cue_path):
    """Mapeia cada FILE do CUE para um BIN existente na mesma pasta."""
    referenced = cue_referenced_files(cue_path)
    if not referenced:
        return []

    mapping = []
    missing = []
    used = set()
    for name in referenced:
        child = case_insensitive_child(cue_path.parent, name)
        if child.exists() and child.suffix.lower() == ".bin":
            mapping.append((name, child))
            used.add(str(child.resolve()).lower())
        else:
            missing.append(name)

    if missing:
        available = [
            item
            for item in folder_bin_files(cue_path.parent)
            if str(item.resolve()).lower() not in used
        ]
        if len(available) != len(missing):
            return []
        for name, child in zip(missing, available):
            mapping.append((name, child))

    return mapping


def validate_cue_with_bins(cue_path):
    """Valida um CUE e retorna os BIN existentes referenciados ou equivalentes."""
    return [bin_path for _, bin_path in resolve_cue_bin_map(cue_path)]


def create_basic_cue_for_bin(bin_path):
    """Cria um CUE simples e conservador para um BIN de CD-ROM."""
    cue_path = bin_path.with_suffix(".cue")
    if cue_path.exists():
        return None

    content = (
        f'FILE "{bin_path.name}" BINARY\n'
        "  TRACK 01 MODE2/2352\n"
        "    INDEX 01 00:00:00\n"
    )
    cue_path.write_text(content, encoding="utf-8")
    return cue_path


def create_missing_cues(root_folder):
    """Cria CUEs basicos para BINs que nao possuem CUE correspondente."""
    created = []
    root = Path(root_folder)
    try:
        folders = sorted({bin_path.parent for bin_path in root.rglob("*.bin")})
    except OSError:
        return created

    for folder in folders:
        bins = folder_bin_files(folder)
        if not bins:
            continue

        used_bins = set()
        try:
            cue_paths = sorted(folder.glob("*.cue"), key=lambda item: item.name.lower())
        except OSError:
            cue_paths = []

        for cue_path in cue_paths:
            for _, bin_path in resolve_cue_bin_map(cue_path):
                try:
                    used_bins.add(str(bin_path.resolve()).lower())
                except OSError:
                    pass

        for bin_path in bins:
            try:
                key = str(bin_path.resolve()).lower()
            except OSError:
                continue
            if key in used_bins:
                continue
            try:
                cue_path = create_basic_cue_for_bin(bin_path)
            except OSError:
                cue_path = None
            if cue_path:
                created.append(cue_path)

    return created


def output_chd_path(cue_path, output_folder):
    """Calcula o caminho de saida do CHD na pasta destino."""
    return Path(output_folder) / f"{cue_path.stem}.chd"


def game_size(cue_path, bin_paths):
    """Calcula tamanho estimado do jogo somando CUE e BINs encontrados."""
    total = 0
    paths = [cue_path]
    paths.extend(bin_paths)
    seen = set()
    for item in paths:
        key = str(item.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            total += item.stat().st_size
        except OSError:
            pass
    return total


def build_game_record(cue_path, bin_paths, output_folder=None):
    """Cria o dicionario usado pela GUI e pelos workers para um jogo."""
    chd_path = output_chd_path(cue_path, output_folder or default_output_path())
    exists = chd_path.exists()
    size = game_size(cue_path, bin_paths)
    return {
        "id": str(cue_path.resolve()).lower(),
        "name": cue_path.stem,
        "path": str(cue_path),
        "folder": str(cue_path.parent),
        "chd_path": str(chd_path),
        "size": size,
        "size_text": format_size(size),
        "status": STATUS_EXISTS if exists else STATUS_READY,
        "progress": 100 if exists else 0,
        "selected": not exists,
        "chd_exists": exists,
    }
