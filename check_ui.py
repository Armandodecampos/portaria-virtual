import sys
from PyQt6.QtWidgets import QApplication
from unittest.mock import MagicMock

# Mocking stuff that might fail in headless environment without display
app = QApplication(sys.argv)

try:
    import importlib
    module = importlib.import_module("Portaria Virtual")

    # Mock settings
    mock_parent = MagicMock()
    mock_parent.settings.value.return_value = "light"

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
    # InstrucoesDialog might try to show/exec, so we just check __init__
    d = module.InstrucoesDialog(mock_parent)

    print("UI components instantiated and themed successfully.")

except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
