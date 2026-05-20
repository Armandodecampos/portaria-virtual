import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

# Mocking some things if necessary, but hopefully not.
# We need the app to be imported
from Portaria_Virtual import SmartPortariaScanner

def capture():
    app = QApplication.instance()
    win = SmartPortariaScanner()
    win.aplicar_tema("sepia")
    win.show()

    # Give it a moment to layout
    QTimer.singleShot(1000, lambda: save_and_exit(win))

def save_and_exit(win):
    pixmap = win.grab()
    os.makedirs("/home/jules/verification/screenshots", exist_ok=True)
    pixmap.save("/home/jules/verification/screenshots/sepia_theme.png")
    print("Screenshot saved to /home/jules/verification/screenshots/sepia_theme.png")
    QApplication.quit()

if __name__ == "__main__":
    # Ensure offscreen
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv)
    capture()
    sys.exit(app.exec())
