"""Ponto de entrada do CHD Batch Converter."""

import sys

from PySide6.QtWidgets import QApplication

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
