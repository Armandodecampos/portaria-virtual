import sys
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication, QTextBrowser

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

def test():
    app = QApplication(sys.argv)
    tb = QTextBrowser()
    tb.setFixedSize(450, 400)

    card_bg = "#1e293b"
    border_color = "#475569"

    item1 = f"<div style='background-color: {card_bg}; border: 1px solid {border_color}; border-radius: 0px; padding: 5px 12px; margin: 0px; width: 100%; color: white;'>ID 13695: Armando...</div>"
    item2 = f"<div style='background-color: {card_bg}; border: 1px solid {border_color}; border-radius: 0px; padding: 5px 12px; margin: 0px; margin-top: -1px; width: 100%; color: white;'>ID 12480: Armando...</div>"
    # Selected
    item3 = f"<div style='background-color: {card_bg}; border: 1px solid {border_color}; border-radius: 0px; padding: 5px 12px; margin: 0px; margin-top: -1px; width: 100%; color: white;'><table width='100%' cellpadding='0' cellspacing='0' style='margin: 0; padding: 0; border-collapse: collapse; border: none; vertical-align: top;'><tr><td style='padding-right: 15px; vertical-align: top;'>ID 12430: Armando...</td><td width='30' align='center' valign='top'>➜</td></tr></table></div>"
    item4 = f"<div style='background-color: {card_bg}; border: 1px solid {border_color}; border-radius: 0px; padding: 5px 12px; margin: 0px; margin-top: -1px; width: 100%; color: white;'>ID 12381: Armando...</div>"

    html = f"<html><head><style>body {{ margin: 0; padding: 0; background-color: #0f172a; }} div, table {{ margin: 0; padding: 0; border-collapse: collapse; }}</style></head><body>{item1}{item2}{item3}{item4}</body></html>"

    tb.setHtml(html)
    tb.document().setDocumentMargin(0)
    tb.grab().save("test_gap.png")

if __name__ == "__main__":
    test()
