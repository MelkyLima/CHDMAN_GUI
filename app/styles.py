"""Tema visual escuro do aplicativo."""


APP_STYLE = """
QMainWindow, QWidget {
    background: #16191f;
    color: #e7eaf0;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QMenuBar {
    background: #11141a;
    color: #e7eaf0;
    padding: 4px;
}

QMenuBar::item:selected, QMenu::item:selected {
    background: #2b6cb0;
}

QMenu {
    background: #1d222b;
    color: #e7eaf0;
    border: 1px solid #303744;
}

QFrame#topBar {
    background: #11141a;
    border-bottom: 1px solid #303744;
}

QFrame#statusBar {
    background: #11141a;
    border-top: 1px solid #303744;
}

QLabel#titleLabel {
    font-size: 15pt;
    font-weight: 700;
}

QLabel#mutedLabel {
    color: #aab2c0;
}

QPushButton {
    background: #273241;
    color: #f5f7fb;
    border: 1px solid #3a4658;
    border-radius: 6px;
    padding: 7px 12px;
}

QPushButton:hover {
    background: #334155;
}

QPushButton:pressed {
    background: #1f6fb2;
}

QPushButton:disabled {
    background: #222832;
    color: #778092;
}

QPushButton#primaryButton {
    background: #2b6cb0;
    border-color: #3b82c4;
}

QPushButton#dangerButton {
    background: #8f2d2d;
    border-color: #b54848;
}

QLineEdit, QSpinBox {
    background: #0f1217;
    color: #f5f7fb;
    border: 1px solid #303744;
    border-radius: 6px;
    padding: 7px 9px;
}

QTableWidget {
    background: #171b22;
    alternate-background-color: #1d222b;
    color: #edf2f7;
    border: 1px solid #303744;
    gridline-color: #2d3440;
    selection-background-color: #244c76;
    selection-color: #ffffff;
}

QHeaderView::section {
    background: #11141a;
    color: #d8dee9;
    padding: 7px;
    border: 0;
    border-right: 1px solid #303744;
    border-bottom: 1px solid #303744;
    font-weight: 600;
}

QProgressBar {
    background: #0f1217;
    color: #f5f7fb;
    border: 1px solid #303744;
    border-radius: 5px;
    text-align: center;
    min-height: 18px;
}

QProgressBar::chunk {
    background: #2b6cb0;
    border-radius: 4px;
}

QPlainTextEdit {
    background: #0f1217;
    color: #d8dee9;
    border: 1px solid #303744;
    border-radius: 6px;
    padding: 6px;
}
"""
