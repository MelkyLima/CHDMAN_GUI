"""Ponto de entrada do CHD Batch Converter."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gui import MainWindow


def main():
    """Inicializa a aplicacao Qt."""
    app = QApplication(sys.argv)
    app.setApplicationName("CHD Batch Converter")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
