import sys

from PySide6.QtWidgets import QApplication
from pymodbus import pymodbus_apply_logging_config

from config.loader import load_config
from ui.main_window import MainWindow


def main():
    pymodbus_apply_logging_config("INFO")

    app = QApplication(sys.argv)
    config = load_config()
    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
