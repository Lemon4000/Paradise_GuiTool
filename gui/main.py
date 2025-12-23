import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile
from gui.views.MainWindow import MainWindow

def main():
    try:
        root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        os.chdir(root)
    except Exception:
        pass
    app = QApplication(sys.argv)
    w = MainWindow()
    try:
        f = QFile('gui/resources/style.qss')
        if f.open(QFile.ReadOnly | QFile.Text):
            app.setStyleSheet(f.readAll().data().decode('utf-8'))
    except Exception:
        pass
    w.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
