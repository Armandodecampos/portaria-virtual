import sys
import os
from unittest.mock import MagicMock

# Set the flag before anything else
from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    app = QApplication(sys.argv)

    import importlib
    module = importlib.import_module("Portaria Virtual")

    # Mock settings
    class MockParent(QWidget):
        def __init__(self):
            super().__init__()
            self.settings = MagicMock()
            self.settings.value.return_value = "light"

    mock_parent = MockParent()

    print("Testing ExcelRecordsWidget themes...")
    w = module.ExcelRecordsWidget(mock_parent)
    w.aplicar_tema("light")
    w.aplicar_tema("sepia")
    w.aplicar_tema("dark")

    print("Testing NotificationToast themes...")
    t = module.NotificationToast("test", mock_parent)
    t.apply_toast_theme("light")
    t.apply_toast_theme("sepia")
    t.apply_toast_theme("dark")

    print("Testing InstrucoesDialog themes...")
    d = module.InstrucoesDialog(mock_parent)

    print("UI components instantiated and themed successfully.")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
