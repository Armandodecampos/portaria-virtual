import sys
import os
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest

# Ensure offscreen
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

# Import the app
# We need to mock some things if they are not available, but let's try direct import first.
try:
    from Portaria_Virtual import SmartPortariaScanner
except ImportError:
    # If the filename has spaces, we might need to handle it differently
    import importlib.util
    spec = importlib.util.spec_from_file_location("Portaria_Virtual", "Portaria Virtual.py")
    pv = importlib.util.module_from_spec(spec)
    sys.modules["Portaria_Virtual"] = pv
    spec.loader.exec_module(pv)
    SmartPortariaScanner = pv.SmartPortariaScanner

def verify():
    app = QApplication(sys.argv)
    win = SmartPortariaScanner()
    win.show()

    # Wait for initialization
    QTest.qWait(1000)

    # Check if input_busca_cpf exists
    if not hasattr(win, 'input_busca_cpf'):
        print("Error: input_busca_cpf not found")
        sys.exit(1)

    # Type CPF
    win.input_busca_cpf.setText("12345678901")
    QTest.qWait(500)

    # Check formatting (not in the input itself, but we can check the behavior)
    # The input itself should show the raw numbers or what the user typed unless we added a validator/mask
    # My implementation of formatar_cpf is used in executar_busca_local

    # Trigger search manually if timer hasn't fired
    win.executar_busca_local()
    QTest.qWait(500)

    # Save screenshot
    os.makedirs("/home/jules/verification/screenshots", exist_ok=True)
    win.grab().save("/home/jules/verification/screenshots/verification.png")
    print("Screenshot saved to /home/jules/verification/screenshots/verification.png")

    win.close()
    app.quit()

if __name__ == "__main__":
    verify()
