import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from Portaria_Virtual import ConfigDialog, SmartPortariaScanner

def capture():
    app = QApplication.instance()
    win = SmartPortariaScanner()
    dlg = ConfigDialog(win)
    dlg.show()

    QTimer.singleShot(1000, lambda: save_and_exit(dlg))

def save_and_exit(dlg):
    pixmap = dlg.grab()
    os.makedirs("/home/jules/verification/screenshots", exist_ok=True)
    pixmap.save("/home/jules/verification/screenshots/config_sepia.png")
    print("Screenshot saved to /home/jules/verification/screenshots/config_sepia.png")
    QApplication.quit()

if __name__ == "__main__":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv)
    capture()
    sys.exit(app.exec())
