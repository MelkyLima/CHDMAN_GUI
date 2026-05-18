from pathlib import Path

from app.utils import cue_referenced_files, create_basic_cue_for_bin, format_size, resolve_cue_bin_map


def test_format_size_bytes_and_kb():
    assert format_size(999) == "999 B"
    assert format_size(1024) == "1.00 KB"


def test_cue_referenced_files_parses_file_entries(tmp_path: Path):
    cue = tmp_path / "game.cue"
    cue.write_text('FILE "track01.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    assert cue_referenced_files(cue) == ["track01.bin"]


def test_create_basic_cue_for_bin(tmp_path: Path):
    bin_file = tmp_path / "disc.bin"
    bin_file.write_bytes(b"00")

    cue = create_basic_cue_for_bin(bin_file)

    assert cue is not None
    assert cue.exists()
    assert 'FILE "disc.bin" BINARY' in cue.read_text(encoding="utf-8")


def test_resolve_cue_bin_map_case_insensitive(tmp_path: Path):
    cue = tmp_path / "disc.cue"
    bin_file = tmp_path / "TRACK01.BIN"
    bin_file.write_bytes(b"00")
    cue.write_text('FILE "track01.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")

    mapping = resolve_cue_bin_map(cue)

    assert len(mapping) == 1
    assert mapping[0][1].name == "TRACK01.BIN"
