import sys
import os
import sqlite3
import unicodedata
import re
import datetime
import traceback
import time
import requests
import urllib3
import base64
import json

# --- BLOCO DE PROTEÇÃO DE IMPORTAÇÃO ---
try:
    from PyQt6.QtCore import (
        Qt, QUrl, QTimer, QSettings, QSize, pyqtSignal, QMimeData,
        QPropertyAnimation, QEasingCurve, QPoint, QThread
    )
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLineEdit, QPushButton, QLabel, QSplitter, QTextEdit, QTextBrowser, QGroupBox,
        QStackedWidget, QTabBar, QMessageBox, QDialog, QFileDialog, QFrame,
        QRadioButton, QButtonGroup, QInputDialog, QSizePolicy, QScrollArea, QCheckBox,
        QListWidget, QListWidgetItem
    )
    from PyQt6.QtGui import QPixmap, QFont, QIcon, QAction, QImage
    from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession, QVideoSink, QMediaDevices
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
    import qrcode
    import openpyxl
    import xlrd
    from PIL.ImageQt import ImageQt

    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.keys import Keys

except ImportError as e:
    print("\n" + "="*60)
    print("ERRO CRÍTICO: BIBLIOTECAS NÃO ENCONTRADAS")
    print("="*60)
    print(f"Erro detalhado: {e}")
    print("\nPara corrigir, abra o terminal e digite:")
    print("pip install PyQt6 PyQt6-WebEngine pillow qrcode selenium requests openpyxl xlrd")
    print("="*60 + "\n")
    sys.exit(1)

# --- CLASSE CUSTOMIZADA PARA NAVEGAÇÃO COM ABAS ---
class CustomWebPage(QWebEnginePage):
    """
    Página customizada que abre links em novas abas.
    """
    def __init__(self, profile, parent_view, browser_window):
        super().__init__(profile, parent_view)
        self.browser_window = browser_window

    def createWindow(self, _type):
        for i in range(self.browser_window.tabs.count()):
            tab_text = self.browser_window.tabs.tabText(i)
            if "Portaria Virtual" in tab_text or "ZK Bio" in tab_text:
                self.browser_window.tabs.setCurrentIndex(i)
                view = self.browser_window.web_stack.widget(i)
                if view:
                    return view.page()

        current_profile = self.profile()
        new_view = self.browser_window.add_new_tab(QUrl(""), "Nova Guia", profile=current_profile)
        return new_view.page()

class QRDialog(QDialog):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Code Gerado")
        self.setModal(True)
        self.setStyleSheet("background-color: white; color: black;")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        layout = QVBoxLayout(self)
        layout.addStretch()

        self.lbl_qr = QLabel()
        self.lbl_qr.setPixmap(pixmap)
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_qr)

        self.btn_close = QPushButton("Fechar")
        self.btn_close.setFixedWidth(200)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 8px;
                font-size: 16px;
                margin-top: 20px;
                border: none;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        self.showFullScreen()

# --- NOVA CLASSE: DIÁLOGO DE CÂMERA ---
class CameraDialog(QDialog):
    # Sinal para atualizar a UI com o novo frame com segurança de thread (QImage é mais seguro para threads que QPixmap)
    frame_ready = pyqtSignal(QImage)

    def __init__(self, parent=None, camera_device=None):
        super().__init__(parent)
        self.setWindowTitle("Captura de Foto")
        self.setModal(True)
        self.setMinimumSize(500, 650)
        self.setStyleSheet("background-color: #f8fafc; color: #1e293b;")

        self.layout = QVBoxLayout(self)

        # Área de exibição da câmera
        self.lbl_video = QLabel("Iniciando câmera...")
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setStyleSheet("border: 2px solid #cbd5e1; background-color: black; border-radius: 8px;")
        # Proporção 120:141 -> 400x470 (aprox)
        self.lbl_video.setFixedSize(400, 470)
        self.layout.addWidget(self.lbl_video, alignment=Qt.AlignmentFlag.AlignCenter)

        # Botão principal de captura
        self.btn_capture = QPushButton("📸 Capturar Foto")
        self.btn_capture.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 8px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        self.btn_capture.clicked.connect(self.capture_photo)
        self.layout.addWidget(self.btn_capture)

        # Container para botões pós-captura
        self.container_pos = QWidget()
        self.lay_pos = QHBoxLayout(self.container_pos)

        self.btn_download = QPushButton("💾 Baixar")
        self.btn_download.setStyleSheet("""
            QPushButton { background-color: #10b981; color: white; font-weight: bold; padding: 12px; border-radius: 8px; }
            QPushButton:hover { background-color: #059669; }
        """)

        self.btn_cancel = QPushButton("✖ Cancelar")
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: #ef4444; color: white; font-weight: bold; padding: 12px; border-radius: 8px; }
            QPushButton:hover { background-color: #dc2626; }
        """)

        self.lay_pos.addWidget(self.btn_download)
        self.lay_pos.addWidget(self.btn_cancel)
        self.container_pos.hide()
        self.layout.addWidget(self.container_pos)

        self.btn_download.clicked.connect(self.save_photo)
        self.btn_cancel.clicked.connect(self.reset_camera)

        # Configuração da Câmera
        if camera_device is None:
            camera_device = QMediaDevices.defaultVideoInput()
        self.camera = QCamera(camera_device)
        self.session = QMediaCaptureSession()
        self.sink = QVideoSink()

        self.session.setCamera(self.camera)
        self.session.setVideoSink(self.sink)

        self.sink.videoFrameChanged.connect(self.on_frame_changed)
        self.frame_ready.connect(self.update_ui_frame)

        self.captured_image = None
        self.last_image = None
        self.camera.start()

    def on_frame_changed(self, frame):
        if self.container_pos.isVisible():
            return

        img = frame.toImage()
        if img.isNull():
            return

        # Forçar Proporção 120:141
        w, h = img.width(), img.height()
        target_ratio = 120 / 141

        if w / h > target_ratio:
            # Muito largo, corta laterais
            new_w = int(h * target_ratio)
            offset = (w - new_w) // 2
            img = img.copy(offset, 0, new_w, h)
        else:
            # Muito alto, corta topo/fundo
            new_h = int(w / target_ratio)
            offset = (h - new_h) // 2
            img = img.copy(0, offset, w, new_h)

        self.last_image = img
        self.frame_ready.emit(img)

    def update_ui_frame(self, image):
        pixmap = QPixmap.fromImage(image)
        self.lbl_video.setPixmap(pixmap.scaled(
            self.lbl_video.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def capture_photo(self):
        if self.last_image:
            self.captured_image = self.last_image
            self.btn_capture.hide()
            self.container_pos.show()

    def reset_camera(self):
        self.container_pos.hide()
        self.btn_capture.show()
        self.captured_image = None

    def save_photo(self):
        if self.captured_image:
            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads", "foto_visitante.jpg")
            fname, _ = QFileDialog.getSaveFileName(self, "Salvar Foto", downloads_path, "Images (*.jpg *.png)")
            if fname:
                if self.captured_image.save(fname):
                    QMessageBox.information(self, "Sucesso", "Foto salva com sucesso!")
                    self.accept()
                else:
                    QMessageBox.critical(self, "Erro", "Falha ao salvar a foto.")

    def closeEvent(self, event):
        self.camera.stop()
        super().closeEvent(event)

# --- NOVA CLASSE: NOTIFICAÇÃO TOAST ---
class NotificationToast(QFrame):
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(220, 60)
        self.is_hiding = False

        # Layout principal
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(15, 5, 15, 5)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Ícone ou indicador (opcional, mas bom para o layout)
        self.lbl_icon = QLabel("🔔")
        self.lbl_icon.setStyleSheet("font-size: 18px;")
        self.main_layout.addWidget(self.lbl_icon)

        # Mensagem
        self.lbl_msg = QLabel(message)
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.main_layout.addWidget(self.lbl_msg, 1)

        # Botão Fechar
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide_notification)
        self.main_layout.addWidget(self.btn_close)

        # Timer para auto-fechamento
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_notification)

    def apply_toast_theme(self, mode):
        if mode == "dark":
            bg_color = "#1e293b"
            text_color = "#e2e8f0"
            border_color = "#334155"
            close_hover = "#475569"
        else:
            bg_color = "#ffffff"
            text_color = "#1e293b"
            border_color = "#cbd5e1"
            close_hover = "#f1f5f9"

        self.setStyleSheet(f"""
            NotificationToast {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 10px;
            }}
            QLabel {{
                color: {text_color};
                background: transparent;
            }}
            QPushButton {{
                background: transparent;
                color: {text_color};
                border: none;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {close_hover};
            }}
        """)

    def show_notification(self):
        screen_geo = QApplication.primaryScreen().availableGeometry()
        end_x = screen_geo.width() - self.width() - 20
        end_y = screen_geo.height() - self.height() - 20

        # Começa fora da tela (à direita)
        start_x = screen_geo.width()
        self.move(start_x, end_y)
        self.show()

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(500)
        self.anim.setStartValue(QPoint(start_x, end_y))
        self.anim.setEndValue(QPoint(end_x, end_y))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

        # Inicia timer de 10 segundos
        self.timer.start(10000)

    def hide_notification(self):
        self.is_hiding = True
        screen_geo = QApplication.primaryScreen().availableGeometry()
        start_x = self.x()
        start_y = self.y()
        end_x = screen_geo.width() # Volta para fora da tela

        self.anim_hide = QPropertyAnimation(self, b"pos")
        self.anim_hide.setDuration(500)
        self.anim_hide.setStartValue(QPoint(start_x, start_y))
        self.anim_hide.setEndValue(QPoint(end_x, start_y))
        self.anim_hide.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim_hide.finished.connect(self.deleteLater)
        self.anim_hide.start()

# --- NOVA CLASSE: DIÁLOGO DE CONFIGURAÇÕES ---
class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Configurações do Sistema")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        # Define estilo base do diálogo para garantir legibilidade
        self.setStyleSheet("""
            QDialog { font-size: 14px; }
            QGroupBox { font-weight: bold; border: 1px solid #cbd5e1; border-radius: 6px; margin-top: 10px; padding-top: 15px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }
        """)

        layout = QVBoxLayout(self)

        # === SEÇÃO BANCO DE DADOS ===
        gb_db = QGroupBox("Gerenciamento de Banco de Dados")
        lay_db = QVBoxLayout(gb_db)
        
        # Status atual
        status_text = self.parent_window.lbl_status_db.text()
        self.lbl_status = QLabel(status_text)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Copia o estilo do label original, mas ajusta se necessário
        if "Nenhum" in status_text:
            self.lbl_status.setStyleSheet("color: #ef4444; font-weight: bold; margin-bottom: 10px;")
        else:
            self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold; margin-bottom: 10px;")
            
        lay_db.addWidget(self.lbl_status)

        hbox_btns = QHBoxLayout()
        btn_load = QPushButton("📂 Carregar Banco")
        btn_load.setStyleSheet("background-color: #3b82f6; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        btn_load.clicked.connect(self.acao_carregar)
        
        btn_new = QPushButton("✨ Criar Novo")
        btn_new.setStyleSheet("background-color: #10b981; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        btn_new.clicked.connect(self.acao_novo)
        
        hbox_btns.addWidget(btn_load)
        hbox_btns.addWidget(btn_new)
        lay_db.addLayout(hbox_btns)
        layout.addWidget(gb_db)

        # === SEÇÃO APARÊNCIA ===
        gb_theme = QGroupBox("Aparência")
        lay_theme = QHBoxLayout(gb_theme)
        
        self.rb_claro = QRadioButton("Modo Claro")
        self.rb_escuro = QRadioButton("Modo Escuro")
        
        # Grupo lógico
        self.bg_theme = QButtonGroup(self)
        self.bg_theme.addButton(self.rb_claro, 1)
        self.bg_theme.addButton(self.rb_escuro, 2)
        
        # Define seleção atual
        current_theme = self.parent_window.settings.value("theme", "light")
        if current_theme == "dark":
            self.rb_escuro.setChecked(True)
        else:
            self.rb_claro.setChecked(True)
            
        self.bg_theme.idClicked.connect(self.trocar_tema)
        
        lay_theme.addWidget(self.rb_claro)
        lay_theme.addWidget(self.rb_escuro)
        layout.addWidget(gb_theme)

        # === SEÇÃO CREDENCIAIS ===
        gb_creds = QGroupBox("Credenciais de Acesso")
        lay_creds = QVBoxLayout(gb_creds)

        lay_portaria = QHBoxLayout()
        lay_portaria.addWidget(QLabel("Portaria:"))
        self.edit_portaria_user = QLineEdit(self.parent_window.creds['portaria_user'])
        self.edit_portaria_user.setPlaceholderText("Usuário")
        self.edit_portaria_pass = QLineEdit(self.parent_window.creds['portaria_pass'])
        self.edit_portaria_pass.setPlaceholderText("Senha")
        self.edit_portaria_pass.setEchoMode(QLineEdit.EchoMode.Password)
        lay_portaria.addWidget(self.edit_portaria_user)
        lay_portaria.addWidget(self.edit_portaria_pass)
        lay_creds.addLayout(lay_portaria)

        lay_zk = QHBoxLayout()
        lay_zk.addWidget(QLabel("ZK Bio:  "))
        self.edit_zk_user = QLineEdit(self.parent_window.creds['zk_user'])
        self.edit_zk_user.setPlaceholderText("Usuário")
        self.edit_zk_pass = QLineEdit(self.parent_window.creds['zk_pass'])
        self.edit_zk_pass.setPlaceholderText("Senha")
        self.edit_zk_pass.setEchoMode(QLineEdit.EchoMode.Password)
        lay_zk.addWidget(self.edit_zk_user)
        lay_zk.addWidget(self.edit_zk_pass)
        lay_creds.addLayout(lay_zk)

        btn_save_creds = QPushButton("💾 Salvar Credenciais")
        btn_save_creds.setStyleSheet("background-color: #2563eb; color: white; padding: 8px; border-radius: 4px; font-weight: bold; margin-top: 5px;")
        btn_save_creds.clicked.connect(self.acao_salvar_credenciais)
        lay_creds.addWidget(btn_save_creds)

        layout.addWidget(gb_creds)

        # === RODAPÉ ===
        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(self.accept)
        btn_fechar.setStyleSheet("padding: 8px; margin-top: 10px;")
        layout.addWidget(btn_fechar)

    def acao_carregar(self):
        self.parent_window.abrir_selecao_arquivo()
        self.lbl_status.setText(self.parent_window.lbl_status_db.text()) # Atualiza label local
        if "Ativo" in self.lbl_status.text():
             self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold; margin-bottom: 10px;")

    def acao_novo(self):
        self.parent_window.criar_novo_arquivo()
        self.lbl_status.setText(self.parent_window.lbl_status_db.text()) # Atualiza label local
        if "Ativo" in self.lbl_status.text():
             self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold; margin-bottom: 10px;")

    def trocar_tema(self, id):
        modo = "dark" if id == 2 else "light"
        self.parent_window.aplicar_tema(modo)

    def acao_salvar_credenciais(self):
        p_user = self.edit_portaria_user.text().strip()
        p_pass = self.edit_portaria_pass.text().strip()
        z_user = self.edit_zk_user.text().strip()
        z_pass = self.edit_zk_pass.text().strip()

        if not p_user or not p_pass or not z_user or not z_pass:
            QMessageBox.warning(self, "Aviso", "Todos os campos de credenciais devem ser preenchidos.")
            return

        self.parent_window.settings.setValue("portaria_user", p_user)
        self.parent_window.settings.setValue("portaria_pass", p_pass)
        self.parent_window.settings.setValue("zk_user", z_user)
        self.parent_window.settings.setValue("zk_pass", z_pass)

        self.parent_window.carregar_credenciais()
        QMessageBox.information(self, "Sucesso", "Credenciais salvas com sucesso!")

class InstrucoesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instrução para cadastramento")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        # Tema
        theme = parent.settings.value("theme", "light") if parent else "light"
        if theme == "dark":
            self.setStyleSheet("background-color: #1e293b; color: #e2e8f0;")
            link_color = "#38bdf8"
        else:
            self.setStyleSheet("background-color: #ffffff; color: #1e293b;")
            link_color = "#2563eb"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setReadOnly(True)
        self.browser.setStyleSheet("border: none; background: transparent;")

        texto_html = f"""
        <div style="font-family: sans-serif; line-height: 1.5;">
            <b style="font-size: 18px;">Guia de Liberação: Portaria Virtual</b><br>
            Para garantir o acesso de visitantes ao escritório, o anfitrião deve seguir as instruções de acordo com a sua área de atuação:<br><br>

            <b style="font-size: 16px; color: {link_color};">Anfitriões do Global</b><br>
            Anfitriões das bandas V à I devem realizar o convite diretamente pelo site <a href="https://portaria-global.governarti.com.br/" style="color: {link_color}; text-decoration: none;">portaria-global.governarti.com.br</a>, preenchendo os seguintes dados:<br><br>

            • Nome completo<br>
            • CPF (Para estrangeiros: altere o país no sistema para habilitar outros documentos)<br>
            • E-mail e Telefone<br>
            • Período de liberação<br><br>

            <b>Próximo passo:</b> Após o envio, o visitante receberá um e-mail com o link para cadastro. A autorização de acesso será emitida automaticamente após a conclusão.<br><br>

            <i><b>Nota:</b> Em caso de instabilidade no sistema, a liberação pode ser solicitada via time de Facilities ou BPs.</i><br><br>

            <b style="font-size: 16px; color: {link_color};">Anfitriões do BEES</b><br>
            O anfitrião deve solicitar a liberação enviando um e-mail para <a href="mailto:facilities.bees@ab-inbev.com" style="color: {link_color}; text-decoration: none;">facilities.bees@ab-inbev.com</a> com as seguintes informações:<br><br>

            • Nome completo<br>
            • CPF ou documento de identidade (se estrangeiro)<br>
            • E-mail e Telefone<br>
            • Período de liberação<br><br>

            <b>Próximo passo:</b> O visitante receberá o link de cadastro da Portaria Virtual por e-mail. A entrada será autorizada assim que o registro for finalizado.<br><br>
        </div>
        """
        self.browser.setHtml(texto_html)
        layout.addWidget(self.browser)

        btn_layout = QHBoxLayout()

        self.btn_copy = QPushButton("📋 Copiar todo o texto")
        self.btn_copy.setFixedWidth(200)
        self.btn_copy.clicked.connect(self.copiar_texto)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 8px;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)

        self.btn_fechar = QPushButton("Fechar")
        self.btn_fechar.setFixedWidth(200)
        self.btn_fechar.clicked.connect(self.accept)
        self.btn_fechar.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 8px;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover { background-color: #dc2626; }
        """)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_copy)
        btn_layout.addWidget(self.btn_fechar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.showFullScreen()

    def copiar_texto(self):
        self.browser.selectAll()
        self.browser.copy()

        # Desmarcar para não ficar azul
        cursor = self.browser.textCursor()
        cursor.clearSelection()
        self.browser.setTextCursor(cursor)

        QMessageBox.information(self, "Sucesso", "Texto formatado copiado para a área de transferência!")

class SearchThread(QThread):
    results_ready = pyqtSignal(str, int)

    def __init__(self, search_query, visible_depts, theme_data):
        super().__init__()
        self.search_query = search_query
        self.visible_depts = visible_depts
        self.td = theme_data # card_bg, card_border, text_color, sub_text_color

    def normalize_text(self, text):
        if not text: return ""
        return "".join(
            c for c in unicodedata.normalize('NFD', str(text))
            if unicodedata.category(c) != 'Mn'
        ).lower()

    def render_item_card(self, item):
        extra = []
        if item['email'] != "-": extra.append(f"📧 {item['email']}")
        if item['celular'] != "-": extra.append(f"📱 {item['celular']}")
        if item['cartao'] != "-": extra.append(f"🪪 {item['cartao']}")
        extra_str = " | ".join(extra)

        return f"""
        <div style='background-color: {self.td["card_bg"]}; border: 1px solid {self.td["card_border"]}; border-radius: 6px; padding: 8px; margin-bottom: 5px; word-wrap: break-word;'>
            <div style='font-size: 13px; color: {self.td["text_color"]};'>
                <b style='color: #3b82f6;'>👤 {item['nome']} {item['sobrenome']}</b> (ID: {item['id']})<br>
                <span style='color: {self.td["sub_text_color"]}; font-size: 12px;'>{extra_str}</span>
            </div>
        </div>
        """

    def run(self):
        db_file = "zk_cache.db"
        if not os.path.exists(db_file): return

        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("PRAGMA query_only = ON")
            cursor.execute("PRAGMA cache_size = -10000")

            if self.search_query:
                base_query = """
                    FROM zk_records
                    JOIN zk_records_fts ON zk_records.rowid = zk_records_fts.rowid
                    WHERE zk_records.dept IN ({})
                """.format(",".join(["?"] * len(self.visible_depts)))
                params = list(self.visible_depts)
                for word in self.search_query.split():
                    base_query += " AND zk_records_fts.search_text LIKE ?"
                    params.append(f"%{word}%")
            else:
                base_query = "FROM zk_records WHERE dept IN ({})".format(",".join(["?"] * len(self.visible_depts)))
                params = list(self.visible_depts)

            cursor.execute("SELECT COUNT(*) " + base_query, params)
            total_count = cursor.fetchone()[0]

            # Limitamos para 300 para performance máxima
            query = "SELECT id, nome, sobrenome, dept, celular, cartao, email " + base_query + " ORDER BY dept, nome LIMIT 300"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            html_parts = ["<div style='font-family: sans-serif;'>"]
            if total_count > 300:
                html_parts.append(f"<p style='color: #ef4444; font-weight: bold; background: #fee2e2; padding: 10px; border-radius: 5px;'>⚠️ Exibindo 300 de {total_count} resultados. Refine a busca.</p>")

            current_dept = None
            for r in rows:
                item_data = {"id": r[0], "nome": r[1], "sobrenome": r[2], "dept": r[3], "celular": r[4], "cartao": r[5], "email": r[6]}
                if item_data["dept"] != current_dept:
                    current_dept = item_data["dept"]
                    html_parts.append(f"<h3 style='color: #3b82f6; border-bottom: 1px solid {self.td['card_border']}; margin-top: 15px; margin-bottom: 10px;'>{current_dept}</h3>")
                html_parts.append(self.render_item_card(item_data))

            html_parts.append("</div>")
            self.results_ready.emit("".join(html_parts), total_count)
            conn.close()
        except Exception as e:
            print(f"Erro na thread de busca: {e}")

class ExcelRecordsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.db_conn = None
        self.search_thread = None

        # Tema
        self.theme = parent.settings.value("theme", "light") if parent else "light"
        self.setup_ui()
        self.department_checkboxes = {}
        self.load_from_cache()

    def get_db_conn(self):
        db_file = "zk_cache.db"
        if not self.db_conn:
            try:
                self.db_conn = sqlite3.connect(db_file, check_same_thread=False)
                c = self.db_conn.cursor()
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA cache_size = -10000") # 10MB cache
                c.execute("PRAGMA temp_store = MEMORY")
            except: pass
        return self.db_conn

    def setup_ui(self):
        if self.theme == "dark":
            self.setStyleSheet("background-color: #0f172a; color: #e2e8f0;")
            self.card_bg = "#1e293b"
            self.card_border = "#334155"
            self.text_color = "#f8fafc"
            self.sub_text_color = "#94a3b8"
        else:
            self.setStyleSheet("background-color: #f8fafc; color: #1e293b;")
            self.card_bg = "#ffffff"
            self.card_border = "#cbd5e1"
            self.text_color = "#1e293b"
            self.sub_text_color = "#64748b"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Cabeçalho: Selecionar Arquivo
        header_lay = QHBoxLayout()
        self.btn_upload = QPushButton("Selecionar arquivo Excel")
        self.btn_upload.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-weight: bold;
                padding: 10px 15px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        self.btn_upload.clicked.connect(self.import_excel)
        header_lay.addWidget(self.btn_upload)

        self.lbl_file_name = QLabel("")
        self.lbl_file_name.setStyleSheet("font-style: italic; color: #94a3b8;")
        header_lay.addWidget(self.lbl_file_name)
        header_lay.addStretch()
        layout.addLayout(header_lay)

        self.lbl_count = QLabel("Total de pessoas: 0")
        self.lbl_count.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(self.lbl_count)

        # Filtro de Departamento
        self.btn_toggle_filter = QPushButton("🔍 Filtrar por Departamento")
        self.btn_toggle_filter.setStyleSheet("""
            QPushButton {
                background-color: #475569;
                color: white;
                padding: 8px 12px;
                border-radius: 5px;
                text-align: left;
            }
        """)
        # layout.addWidget(self.btn_toggle_filter)

        self.filter_container = QWidget()
        self.filter_lay = QVBoxLayout(self.filter_container)

        self.cb_all = QCheckBox("Marcar Todos/Desmarcar Todos")
        self.cb_all.clicked.connect(self.toggle_all_departments)
        self.filter_lay.addWidget(self.cb_all)

        self.scroll_depts = QScrollArea()
        self.scroll_depts.setWidgetResizable(True)
        self.scroll_depts.setFixedHeight(150)
        self.depts_widget = QWidget()
        self.depts_layout = QVBoxLayout(self.depts_widget)
        self.scroll_depts.setWidget(self.depts_widget)
        self.filter_lay.addWidget(self.scroll_depts)

        self.filter_container.hide()
        self.btn_toggle_filter.clicked.connect(lambda: self.filter_container.setVisible(not self.filter_container.isVisible()))
        # layout.addWidget(self.filter_container)

        # Pesquisa
        search_lay = QHBoxLayout()
        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("🔍 Pesquisar...")
        self.input_search.setStyleSheet(f"border-radius: 20px; padding: 10px 15px; border: 2px solid {self.card_border};")

        self.timer_busca = QTimer()
        self.timer_busca.setSingleShot(True)
        self.timer_busca.timeout.connect(self.filter_and_render)
        self.input_search.textChanged.connect(lambda: self.timer_busca.start(500))

        self.btn_clear = QPushButton("Apagar")
        self.btn_clear.setStyleSheet("background-color: #ef4444; color: white; padding: 8px 15px; border-radius: 20px;")
        self.btn_clear.clicked.connect(self.input_search.clear)
        self.btn_clear.hide()
        self.input_search.textChanged.connect(lambda t: self.btn_clear.setVisible(len(t)>0))

        search_lay.addWidget(self.input_search)
        search_lay.addWidget(self.btn_clear)
        # layout.addLayout(search_lay)

        # Lista de resultados (usando QTextBrowser para renderização rápida de HTML)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.browser)

        # Botão Fechar
        self.btn_close = QPushButton("Fechar")
        self.btn_close.clicked.connect(self.fechar_ou_ocultar)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 8px;
                margin-top: 10px;
            }
        """)
        layout.addWidget(self.btn_close)

    def normalize_text(self, text):
        if not text: return ""
        return "".join(
            c for c in unicodedata.normalize('NFD', str(text))
            if unicodedata.category(c) != 'Mn'
        ).lower()

    def toggle_all_departments(self):
        checked = self.cb_all.isChecked()
        for cb in self.department_checkboxes.values():
            cb.setChecked(checked)
        self.filter_and_render()

    def load_from_cache(self):
        db_file = "zk_cache.db"
        if os.path.exists(db_file):
            # Verifica integridade do FTS
            try:
                conn = self.get_db_conn()
                if not conn: return
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='zk_records_fts'")
                if not cursor.fetchone():
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='zk_records'")
                    if cursor.fetchone():
                        print("🛠️ Migrando banco de dados para suporte FTS5...")
                        cursor.execute("DROP TABLE IF EXISTS zk_records_fts")
                        cursor.execute("""
                            CREATE VIRTUAL TABLE zk_records_fts USING fts5(
                                search_text,
                                content='zk_records',
                                tokenize='trigram'
                            )
                        """)
                        cursor.execute("INSERT INTO zk_records_fts(rowid, search_text) SELECT rowid, search_text FROM zk_records")
                        conn.commit()
            except Exception as e:
                print(f"Erro ao verificar integridade do cache: {e}")

            self.lbl_file_name.setText("Dados carregados do cache (.db).")
            self.render_department_filters()
            self.filter_and_render()

    def save_to_cache_db(self, new_items):
        db_file = "zk_cache.db"
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=OFF")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.execute("DROP TABLE IF EXISTS zk_records")
            cursor.execute("DROP TABLE IF EXISTS zk_records_fts")
            cursor.execute("""
                CREATE TABLE zk_records (
                    id TEXT, nome TEXT, sobrenome TEXT, dept TEXT,
                    celular TEXT, cartao TEXT, email TEXT, search_text TEXT
                )
            """)
            cursor.execute("""
                CREATE VIRTUAL TABLE zk_records_fts USING fts5(
                    search_text,
                    content='zk_records',
                    tokenize='trigram'
                )
            """)

            records = []
            for dept in new_items:
                for item in new_items[dept]:
                    records.append((
                        item["id"], item["nome"], item["sobrenome"], item["dept"],
                        item["celular"], item["cartao"], item["email"], item["search_text"]
                    ))

            cursor.executemany("INSERT INTO zk_records VALUES (?,?,?,?,?,?,?,?)", records)
            cursor.execute("INSERT INTO zk_records_fts(rowid, search_text) SELECT rowid, search_text FROM zk_records")
            cursor.execute("CREATE INDEX idx_zk_dept_nome ON zk_records(dept, nome)")
            conn.commit()
            conn.close()
            # Reinicia conexão persistente para refletir mudanças
            self.db_conn = None
        except Exception as e:
            print(f"Erro ao salvar cache DB: {e}")

    def render_department_filters(self):
        # Limpa layout anterior
        for i in reversed(range(self.depts_layout.count())):
            self.depts_layout.itemAt(i).widget().setParent(None)

        self.department_checkboxes = {}
        db_file = "zk_cache.db"
        if not os.path.exists(db_file): return

        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("PRAGMA query_only = ON")
            cursor.execute("SELECT dept, COUNT(*) FROM zk_records GROUP BY dept ORDER BY dept")
            rows = cursor.fetchall()
            for dept, count in rows:
                cb = QCheckBox(f"{dept} ({count})")
                cb.setChecked(True)
                cb.clicked.connect(self.filter_and_render)
                self.depts_layout.addWidget(cb)
                self.department_checkboxes[dept] = cb
            conn.close()
        except: pass
        self.cb_all.setChecked(True)

    def import_excel(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Selecionar Excel", "", "Excel Files (*.xls *.xlsx)")
        if not fname: return

        try:
            self.lbl_file_name.setText(f"📂 {os.path.basename(fname)}")

            rows = []
            if fname.lower().endswith(".xls"):
                wb = xlrd.open_workbook(fname)
                ws = wb.sheet_by_index(0)
                for row_idx in range(1, ws.nrows):
                    rows.append(ws.row_values(row_idx))
            else:
                wb = openpyxl.load_workbook(fname, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(min_row=2, values_only=True):
                    rows.append(row)

            new_items = {}
            # Mapping: ID(0), Nome(1), Sobrenome(2), Departamento(4), Celular(7), Cartão(8), Email(9)
            for row in rows:
                if not any(row): continue

                # Use safely indices with get() or similar logic to avoid IndexError
                # or check length
                row_len = len(row)
                vid = str(row[0]) if row_len > 0 and row[0] is not None else "-"
                nome = str(row[1]).strip() if row_len > 1 and row[1] else "-"
                sobrenome = str(row[2]).strip() if row_len > 2 and row[2] else "-"
                dept = str(row[4]).strip() if row_len > 4 and row[4] else "Portaria Virtual"
                celular = str(row[7]) if row_len > 7 and row[7] is not None else "-"
                cartao = str(row[8]) if row_len > 8 and row[8] is not None else "-"
                email = str(row[9]) if row_len > 9 and row[9] is not None else "-"

                if vid == "-" and nome == "-": continue

                search_text = self.normalize_text(f"{nome} {sobrenome} {vid} {email} {celular} {cartao}")

                item = {
                    "id": vid, "nome": nome, "sobrenome": sobrenome,
                    "dept": dept, "celular": celular, "cartao": cartao,
                    "email": email, "search_text": search_text
                }

                if dept not in new_items: new_items[dept] = []
                new_items[dept].append(item)

            self.save_to_cache_db(new_items)
            self.render_department_filters()
            self.filter_and_render()

            if self.parent_window:
                self.parent_window.update_zk_count()

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao importar Excel: {e}")

    def fechar_ou_ocultar(self):
        if self.parent_window:
            self.parent_window.abrir_dialogo_excel()

    def filter_and_render(self, search_text_raw=None):
        if search_text_raw is None:
            search_text_raw = self.input_search.text().strip()
        search_query = self.normalize_text(search_text_raw)

        visible_depts = [dept for dept, cb in self.department_checkboxes.items() if cb.isChecked()]
        if not visible_depts:
            self.browser.clear()
            self.lbl_count.setText("Total de pessoas: 0")
            return

        # Cancela busca anterior se existir
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.terminate()
            self.search_thread.wait()

        theme_data = {
            "card_bg": self.card_bg,
            "card_border": self.card_border,
            "text_color": self.text_color,
            "sub_text_color": self.sub_text_color
        }

        self.search_thread = SearchThread(search_query, visible_depts, theme_data)
        self.search_thread.results_ready.connect(self.on_search_finished)
        self.search_thread.start()

    def on_search_finished(self, html, total_count):
        self.browser.setHtml(html)
        self.lbl_count.setText(f"Total de pessoas: {total_count}")

    def render_item_card(self, item):
        # Este método agora é usado principalmente para importação imediata,
        # mas a thread tem sua própria versão. Mantemos para consistência.
        extra = []
        if item['email'] != "-": extra.append(f"📧 {item['email']}")
        if item['celular'] != "-": extra.append(f"📱 {item['celular']}")
        if item['cartao'] != "-": extra.append(f"🪪 {item['cartao']}")
        extra_str = " | ".join(extra)

        return f"""
        <div style='background-color: {self.card_bg}; border: 1px solid {self.card_border}; border-radius: 6px; padding: 8px; margin-bottom: 5px; word-wrap: break-word;'>
            <div style='font-size: 13px; color: {self.text_color};'>
                <b style='color: #3b82f6;'>👤 {item['nome']} {item['sobrenome']}</b> (ID: {item['id']})<br>
                <span style='color: {self.sub_text_color}; font-size: 12px;'>{extra_str}</span>
            </div>
        </div>
        """

# --- CONFIGURAÇÕES AMBEV ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ['no_proxy'] = '192.168.7.9'

ZK_SERVER = "http://192.168.7.9:8098"

class TransferThread(QThread):
    success = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, id_convite, creds):
        super().__init__()
        self.id_convite = id_convite
        self.creds = creds
        self.driver = None

    def run(self):
        try:
            self.log.emit(f"🚀 Iniciando transferência para ID {self.id_convite}...")
            options = Options()
            options.add_experimental_option("detach", True)
            options.add_argument("--disable-blink-features=AutomationControlled")
            self.driver = webdriver.Chrome(options=options)
            driver = self.driver
            wait = WebDriverWait(driver, 35)

            # PORTARIA
            self.log.emit("🌐 Acessando Portaria...")
            driver.get("https://portaria-global.governarti.com.br/login")
            wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(self.creds['portaria_user'])
            driver.find_element(By.NAME, "password").send_keys(self.creds['portaria_pass'] + Keys.ENTER)

            # EXTRAIR DADOS
            self.log.emit(f"📄 Extraindo dados do convite {self.id_convite}...")
            url_detalhes = f"https://portaria-global.governarti.com.br/visita/{self.id_convite}/detalhes"
            driver.get(url_detalhes)
            # wait.until(EC.presence_of_element_located((By.ID, "img-preview")))
            time.sleep(3)

            # 1. Nome e CPF
            try:
                label_visitante = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(., 'Visitante')]/following::label[1]"))).text
                texto_limpo = " ".join(label_visitante.split())
                cpf_match = re.search(r'(\d{3}\.\d{3}\.\d{3}-\d{2})|(\d{11})', texto_limpo)
                cpf_numeros = re.sub(r'\D', '', cpf_match.group(0)) if cpf_match else ""
                nome_completo = texto_limpo.split("-")[0].strip()
            except:
                nome_completo = "Visitante"
                cpf_numeros = ""

            partes_nome = nome_completo.split(" ")
            primeiro_nome = partes_nome[0]
            sobrenome = " ".join(partes_nome[1:]) if len(partes_nome) > 1 else " "

            # 2. Captura de Telefone
            try:
                tel_raw = driver.find_element(By.XPATH, "//div[contains(text(), 'Telefone')]/following::label[1] | //label[contains(text(), '(')]").text
                telefone_limpo = re.sub(r'\D', '', tel_raw).strip()
            except:
                telefone_limpo = ""

            # 3. Captura de Email
            try:
                email_raw = driver.find_element(By.XPATH, "//div[contains(text(), 'Email')]/following::label[1] | //label[contains(text(), '@')]").text
                email_limpo = email_raw.strip()
                if "unidade" in email_limpo.lower():
                     email_raw = driver.find_element(By.XPATH, "//label[contains(., '@')]").text
                     email_limpo = email_raw.strip()
            except:
                email_limpo = ""

            # img_url = driver.find_element(By.ID, "img-preview").get_attribute("src")
            # path_foto = os.path.abspath(f"temp_visitante_{self.id_convite}.jpg")
            # with open(path_foto, 'wb') as f:
            #     f.write(requests.get(img_url, verify=False).content)

            dados = {
                "primeiro_nome": primeiro_nome, "sobrenome": sobrenome,
                "cpf": cpf_numeros, "telefone": telefone_limpo,
                "email": email_limpo
            }

            # ZK LOGIN
            self.log.emit("🔐 Acessando ZK Server...")
            driver.get(f"{ZK_SERVER}/bioLogin.do")
            wait.until(EC.element_to_be_clickable((By.ID, "username"))).send_keys(self.creds['zk_user'])
            driver.find_element(By.ID, "password").send_keys(self.creds['zk_pass'] + Keys.ENTER)

            # NAVEGAÇÃO
            time.sleep(5)
            driver.get(f"{ZK_SERVER}/main.do?home#basePerson")
            time.sleep(7)

            self.log.emit("➕ Criando novo registro no ZK...")
            btn_novo = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'dhxtoolbar_text') and (text()='Novo' or contains(., 'Novo'))]")))
            btn_novo.click()
            time.sleep(6)

            # PREENCHIMENTO VIA JAVASCRIPT
            script_preencher = """
                function triggerEvents(el) {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }
                var inputs = document.getElementsByTagName('input');
                var d = arguments[0];
                for (var i = 0; i < inputs.length; i++) {
                    if (inputs[i].name == 'name') { inputs[i].value = d.p_nome; triggerEvents(inputs[i]); }
                    if (inputs[i].name == 'lastName') { inputs[i].value = d.s_nome; triggerEvents(inputs[i]); }
                    if (inputs[i].name == 'mobile' || inputs[i].name == 'mobilePhone') { inputs[i].value = d.tel; triggerEvents(inputs[i]); }
                    if (inputs[i].name == 'email') { inputs[i].value = d.eml; triggerEvents(inputs[i]); }
                }
            """
            driver.execute_script(script_preencher, {
                'p_nome': dados['primeiro_nome'],
                's_nome': dados['sobrenome'],
                'tel': dados['telefone'],
                'eml': dados['email']
            })
            time.sleep(1)

            # CPF/PIN
            pin_field = driver.find_element(By.ID, "pers_pin_register_id")
            driver.execute_script("""
                arguments[0].removeAttribute('readonly');
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
            """, pin_field, dados['cpf'])
            time.sleep(1)

            # FOTO
            # driver.find_element(By.CSS_SELECTOR, "input[type='file']").send_keys(dados['path_foto'])
            # time.sleep(2)

            self.success.emit("Dados transferidos")

            # Remove foto temporária com pequeno delay para garantir o envio
            # time.sleep(3)
            # try: os.remove(path_foto)
            # except: pass

        except Exception as e:
            self.error.emit(str(e))
        finally:
            # Não fechamos o driver no finally para permitir que o browser continue aberto após o sucesso.
            # O driver será fechado apenas se stop() for chamado ou se houver erro antes da inicialização completa.
            self.driver = None

    def stop(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.driver = None

class DatabaseHandler:
    @staticmethod
    def remove_accents(input_str):
        if not input_str:
            return ""
        nfkd_form = unicodedata.normalize('NFKD', input_str)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()

    def __init__(self, db_path):
        # Conexão direta com o caminho fornecido pelo usuário via GUI
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.create_function("unaccent", 1, self.remove_accents)
        self.cursor = self.conn.cursor()
        self.criar_tabelas()
        self.migrar_dados_vazios()

    def reprocessar_dados_existentes(self):
        self.cursor.execute("SELECT visita_id, conteudo FROM detalhes_visitas")
        registros = self.cursor.fetchall()
        if registros:
            for vid, conteudo in registros:
                nome, cpf, horario = self.extrair_dados(conteudo)
                self.cursor.execute("UPDATE detalhes_visitas SET nome = ?, cpf = ?, horario = ? WHERE visita_id = ?", (nome, cpf, horario, vid))
            self.conn.commit()

    def migrar_dados_vazios(self):
        self.cursor.execute("SELECT visita_id, conteudo FROM detalhes_visitas WHERE nome IS NULL OR cpf IS NULL OR horario IS NULL")
        vazios = self.cursor.fetchall()
        if vazios:
            for vid, conteudo in vazios:
                nome, cpf, horario = self.extrair_dados(conteudo)
                self.cursor.execute("UPDATE detalhes_visitas SET nome = ?, cpf = ?, horario = ? WHERE visita_id = ?", (nome, cpf, horario, vid))
            self.conn.commit()

    def criar_tabelas(self):
        self.cursor.execute("PRAGMA user_version")
        versao = self.cursor.fetchone()[0]

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS detalhes_visitas (
                visita_id INTEGER PRIMARY KEY,
                nome TEXT,
                cpf TEXT,
                horario TEXT,
                conteudo TEXT,
                url TEXT,
                data_captura TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.cursor.execute("PRAGMA table_info(detalhes_visitas)")
        columns = [col[1] for col in self.cursor.fetchall()]
        if 'nome' not in columns:
            self.cursor.execute("ALTER TABLE detalhes_visitas ADD COLUMN nome TEXT")
        if 'cpf' not in columns:
            self.cursor.execute("ALTER TABLE detalhes_visitas ADD COLUMN cpf TEXT")
        if 'horario' not in columns:
            self.cursor.execute("ALTER TABLE detalhes_visitas ADD COLUMN horario TEXT")

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_nome ON detalhes_visitas(nome)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_cpf ON detalhes_visitas(cpf)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_horario ON detalhes_visitas(horario)")

        if versao < 1:
            self.reprocessar_dados_existentes()
            self.cursor.execute("PRAGMA user_version = 1")
        self.conn.commit()

    def salvar_visita(self, visita_id, nome, cpf, horario, conteudo, url):
        try:
            self.cursor.execute('INSERT OR REPLACE INTO detalhes_visitas (visita_id, nome, cpf, horario, conteudo, url) VALUES (?, ?, ?, ?, ?, ?)',
                               (visita_id, nome, cpf, horario, conteudo, url))
            self.conn.commit()
            return True
        except Exception:
            return False

    def buscar_por_id(self, visita_id):
        try:
            self.cursor.execute("SELECT nome FROM detalhes_visitas WHERE visita_id = ?", (visita_id,))
            res = self.cursor.fetchone()
            return res[0] if res else None
        except Exception:
            return None

    def buscar_por_filtro(self, termos):
        if not termos: return []
        query = "SELECT visita_id, nome, cpf, horario FROM detalhes_visitas WHERE "
        conditions = []
        params = []
        for t in termos:
            t_norm = self.remove_accents(t)
            conditions.append("(unaccent(nome) LIKE ? OR cpf LIKE ?)")
            params.extend([f"%{t_norm}%", f"%{t}%"])
        query += " AND ".join(conditions)
        query += " ORDER BY visita_id DESC LIMIT 50"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def get_maior_id_salvo(self):
        try:
            self.cursor.execute("SELECT MAX(visita_id) FROM detalhes_visitas")
            res = self.cursor.fetchone()
            maior_id = res[0] if res[0] else 0
            return maior_id
        except Exception as e:
            print(f"❌ Erro ao ler maior ID: {e}")
            return 0

    @staticmethod
    def extrair_dados(conteudo):
        if not conteudo:
            return "Desconhecido", "N/A", "N/A"
        reg_nome = r"Visitante:\s*([\w\.\s\-]+)"
        reg_cpf = r"(\d{3}\.\d{3}\.\d{3}-\d{2})"
        reg_horario = r"Horário:\s*(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}\s*-\s*(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}"
        m_nome = re.search(reg_nome, conteudo, re.IGNORECASE)
        m_cpf = re.search(reg_cpf, conteudo)
        m_horario = re.search(reg_horario, conteudo)
        raw_nome = m_nome.group(1).strip() if m_nome else "Desconhecido"
        cpf = m_cpf.group(1) if m_cpf else "N/A"
        horario = f"{m_horario.group(1)} - {m_horario.group(2)}" if m_horario else "N/A"
        if cpf != "N/A" and cpf in raw_nome:
            raw_nome = raw_nome.replace(cpf, "")
        clean_nome = raw_nome.split("Telefone")[0].split("CPF")[0].split("Celular")[0].split("Horário")[0].strip(" -")
        if not clean_nome: clean_nome = "Desconhecido"
        return clean_nome, cpf, horario

class SmartPortariaScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monitor Portaria - Gestão de Dados")
        self.resize(1400, 900)
        
        # Gerenciador de configurações persistentes
        self.settings = QSettings("PortariaApps", "MonitorVisitas")
        
        # INICIALIZA SEM BANCO DE DADOS
        self.db = None
        self.id_atual = 1
        self.rodando = True
        
        self.timer_retry = QTimer()
        self.timer_retry.setSingleShot(True)
        self.timer_retry.timeout.connect(self.carregar_url_id)

        self.profile_anonimo = QWebEngineProfile(self) 
        self.profile_anonimo.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Janela de pesquisa integrada (deve ser criada antes do setup_ui para ser adicionada ao layout)
        self.container_pesquisa_zk = ExcelRecordsWidget(self)
        self.container_pesquisa_zk.hide()

        self.setup_ui()
        self.configurar_navegadores()

        # Carrega credenciais e tema
        self.carregar_credenciais()
        saved_theme = self.settings.value("theme", "light")
        self.aplicar_tema(saved_theme)

        self.timer_busca = QTimer()
        self.timer_busca.setSingleShot(True)
        self.timer_busca.timeout.connect(self.executar_busca_local)

        self.timer_download_img = QTimer()
        self.timer_download_img.timeout.connect(self.verificar_imagem_capturada)
        
        self.add_new_tab(QUrl("https://portaria-global.governarti.com.br/visita/"), "Portaria Virtual", closable=False)
        self.add_new_tab(QUrl("about:blank"), "Guia anônima", closable=False, profile=self.profile_anonimo)
        self.add_new_tab(QUrl(f"{ZK_SERVER}/bioLogin.do"), "ZK Bio", closable=False)
        
        self.tabs.setCurrentIndex(0)
        self.web_stack.setCurrentIndex(0)

        self.txt_live.append(f"--- SISTEMA INICIADO: {datetime.datetime.now().strftime('%H:%M:%S')} ---")
        
        # Tenta carregar automaticamente o último banco usado
        self.carregar_ultimo_banco()
        self.update_zk_count()

        self.active_toast = None

    def setup_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QHBoxLayout(self.central)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PAINEL ESQUERDO ---
        self.painel_lateral = QWidget()
        self.painel_lateral.setFixedWidth(450)
        lat = QVBoxLayout(self.painel_lateral)
        lat.setContentsMargins(5, 5, 5, 5)
        lat.setSpacing(10)

        # === CABEÇALHO DO PAINEL COM BOTÕES DE CONFIG, INSTRUÇÃO E CÂMERA ===
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        header_layout.setContentsMargins(5, 5, 5, 5)
        
        self.btn_config = QPushButton("⚙️")
        self.btn_config.setToolTip("Configurações")
        self.btn_config.setFixedSize(38, 38)
        self.btn_config.clicked.connect(self.abrir_configuracoes)

        self.btn_instrucao = QPushButton("📖")
        self.btn_instrucao.setToolTip("Instrução")
        self.btn_instrucao.setFixedSize(38, 38)
        self.btn_instrucao.clicked.connect(self.abrir_instrucoes)

        self.btn_abrir_camera = QPushButton("📷")
        self.btn_abrir_camera.setToolTip("Abrir Câmera")
        self.btn_abrir_camera.setFixedSize(38, 38)
        self.btn_abrir_camera.clicked.connect(self.abrir_camera)

        self.btn_unlock = QPushButton("🔓")
        self.btn_unlock.setToolTip("Destravar")
        self.btn_unlock.setFixedSize(38, 38)
        self.btn_unlock.clicked.connect(self.executar_desbloqueio)

        self.btn_upload_excel = QPushButton("📁")
        self.btn_upload_excel.setToolTip("Importar Excel")
        self.btn_upload_excel.setFixedSize(38, 38)
        self.btn_upload_excel.clicked.connect(self.importar_excel_zk)

        self.btn_zk_count = QPushButton("0 registros no Zk Bio")
        self.btn_zk_count.setToolTip("Ver registros do Zk Bio")
        self.btn_zk_count.setFixedHeight(38)
        self.btn_zk_count.setMinimumWidth(240) # Garante que o texto caiba sem cortar
        self.btn_zk_count.clicked.connect(self.abrir_dialogo_excel)

        self.btn_transferir = QPushButton("🚀")
        self.btn_transferir.setToolTip("Transferir")
        self.btn_transferir.setFixedSize(38, 38)
        self.btn_transferir.clicked.connect(lambda: self.iniciar_transferencia())

        self.btn_download_img = QPushButton("📥")
        self.btn_download_img.setToolTip("Baixar Imagem")
        self.btn_download_img.setFixedSize(38, 38)
        self.btn_download_img.clicked.connect(self.ativar_modo_download_imagem)

        self.input_transfer_id = QLineEdit()
        self.input_transfer_id.setPlaceholderText("ID...")
        self.input_transfer_id.setFixedWidth(80)
        self.input_transfer_id.setFixedHeight(38)

        header_layout.addWidget(self.btn_config)
        header_layout.addWidget(self.btn_instrucao)
        header_layout.addWidget(self.btn_abrir_camera)
        header_layout.addWidget(self.btn_transferir)
        header_layout.addWidget(self.btn_download_img)
        header_layout.addWidget(self.btn_unlock)
        header_layout.addWidget(self.btn_upload_excel)
        header_layout.addWidget(self.btn_zk_count)
        header_layout.addWidget(self.input_transfer_id)
        self.input_transfer_id.hide()
        header_layout.addStretch()
        lat.addLayout(header_layout)

        # Pequeno status do banco no painel
        self.lbl_status_db = QLabel("⚠️ Nenhum banco carregado")
        self.lbl_status_db.setStyleSheet("color: #ef4444; font-weight: bold; margin-bottom: 5px; font-size: 11px;")
        self.lbl_status_db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lbl_status_db.hide()
        lat.addWidget(self.lbl_status_db)

        # === GRUPO BUSCA NO BANCO ===
        group_busca = QGroupBox("BUSCA NO BANCO DE DADOS")
        layout_busca = QVBoxLayout(group_busca)
        
        busca_input_layout = QHBoxLayout()
        busca_input_layout.setContentsMargins(0, 0, 0, 0)
        busca_input_layout.setSpacing(5)

        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Digite para buscar...")
        self.input_busca.textChanged.connect(self.realizar_busca_local)
        
        self.btn_limpar_busca = QPushButton("Apagar")
        self.btn_limpar_busca.setFixedWidth(70)
        self.btn_limpar_busca.clicked.connect(self.input_busca.clear)

        busca_input_layout.addWidget(self.input_busca)
        busca_input_layout.addWidget(self.btn_limpar_busca)
        
        layout_busca.addLayout(busca_input_layout)
        
        self.txt_res_busca = QTextBrowser()
        self.txt_res_busca.setOpenExternalLinks(False)
        # O estilo base transparente é bom, mas vamos deixar o tema controlar a cor do texto
        self.txt_res_busca.setStyleSheet("border: none; background: transparent;")
        self.txt_res_busca.anchorClicked.connect(self.abrir_link_resultado)
        layout_busca.addWidget(self.txt_res_busca)
        lat.addWidget(group_busca, 3)

        # === GRUPO LOG ===
        group_live = QGroupBox("LOG DO SISTEMA")
        layout_live = QVBoxLayout(group_live)
        self.txt_live = QTextEdit()
        self.txt_live.setReadOnly(True)
        # Fonte monospace fixa, mas cores geridas pelo tema
        self.txt_live.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        layout_live.addWidget(self.txt_live)
        lat.addWidget(group_live, 2)


        # === GRUPO EXTRATOR DE LINK ===
        group_qr = QGroupBox("EXTRATOR DE LINK")
        group_qr.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout_qr = QVBoxLayout(group_qr)
        self.txt_qr_input = QTextEdit()
        self.txt_qr_input.setPlaceholderText("Cole a mensagem aqui para extrair o link...")
        self.txt_qr_input.setFixedHeight(65)
        layout_qr.addWidget(self.txt_qr_input)

        btns_layout = QHBoxLayout()
        self.btn_open_anon = QPushButton("Abrir na Guia Anônima")
        self.btn_open_anon.clicked.connect(self.abrir_qr_na_anonima)

        self.btn_gen_qr = QPushButton("Gerar QR Code")
        self.btn_gen_qr.clicked.connect(self.mostrar_qr_code)

        self.btn_clear_qr = QPushButton("Apagar")
        self.btn_clear_qr.setFixedWidth(70)
        self.btn_clear_qr.clicked.connect(self.txt_qr_input.clear)

        btns_layout.addWidget(self.btn_open_anon)
        btns_layout.addWidget(self.btn_gen_qr)
        btns_layout.addWidget(self.btn_clear_qr)
        layout_qr.addLayout(btns_layout)
        lat.addWidget(group_qr)

        # --- NAVEGADOR PRINCIPAL ---
        container_web = QWidget()
        layout_web = QVBoxLayout(container_web)
        layout_web.setContentsMargins(5, 5, 5, 5)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.setContentsMargins(5, 5, 5, 5)
        self.btn_back = QPushButton("←")
        self.btn_back.setFixedSize(38, 38)
        self.btn_forward = QPushButton("→")
        self.btn_forward.setFixedSize(38, 38)
        self.btn_reload = QPushButton("↻")
        self.btn_reload.setFixedSize(38, 38)

        self.btn_back.clicked.connect(self.navegar_voltar)
        self.btn_forward.clicked.connect(self.navegar_avancar)
        self.btn_reload.clicked.connect(self.recarregar_pagina)
        
        self.btn_home = QPushButton("🏠")
        self.btn_home.setToolTip("Página Inicial")
        self.btn_home.setFixedSize(38, 38)
        self.btn_home.clicked.connect(self.ir_para_home)

        self.address_bar = QLineEdit()
        self.address_bar.setFixedHeight(38)
        self.address_bar.setPlaceholderText("Introduza o URL...")
        self.address_bar.returnPressed.connect(self.ir_para_url)

        self.tabs = QTabBar()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        # Estilos do TabBar agora serão definidos no aplicar_tema
        self.tabs.tabCloseRequested.connect(self.fechar_aba)
        self.tabs.currentChanged.connect(self.mudar_aba)

        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_reload)
        toolbar.addWidget(self.btn_home)
        toolbar.addWidget(self.address_bar)
        toolbar.addWidget(self.tabs)
        layout_web.addLayout(toolbar)

        # Stack para navegação e pesquisa
        self.stack_central = QStackedWidget()

        self.web_stack = QStackedWidget()
        self.stack_central.addWidget(self.web_stack)

        # Adiciona o container de pesquisa no stack central
        self.stack_central.addWidget(self.container_pesquisa_zk)

        layout_web.addWidget(self.stack_central)

        self.view_worker = QWebEngineView()
        self.view_worker.setVisible(False)
        self.view_worker.loadFinished.connect(self.on_worker_load_finished)
        
        splitter.addWidget(self.painel_lateral)
        splitter.addWidget(container_web)
        layout.addWidget(splitter)

    # === LÓGICA DE TEMAS ===
    def carregar_credenciais(self):
        """Carrega credenciais do QSettings ou usa padrões"""
        self.creds = {
            'portaria_user': self.settings.value("portaria_user", "armando.junior"),
            'portaria_pass': self.settings.value("portaria_pass", "armandocampos.1"),
            'zk_user': self.settings.value("zk_user", "armando.campos"),
            'zk_pass': self.settings.value("zk_pass", "armandocampos.1")
        }

    def aplicar_tema(self, modo):
        self.settings.setValue("theme", modo)
        
        if modo == "dark":
            # Estilo ESCURO
            style = """
                QMainWindow, QWidget { background-color: #0f172a; color: #e2e8f0; }
                QLineEdit { background-color: #1e293b; color: #e2e8f0; border: 1px solid #475569; padding: 6px; border-radius: 4px; }
                QTextEdit { background-color: #1e293b; color: #e2e8f0; border: 1px solid #475569; border-radius: 4px; }
                QGroupBox { border: 1px solid #475569; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #94a3b8; }
                QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
                QLabel { color: #e2e8f0; }
                QPushButton { background-color: #334155; color: white; border: 1px solid #475569; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #475569; }
                QTabBar::tab { background: #1e293b; color: #94a3b8; border: 1px solid #475569; padding: 8px 30px 8px 12px; border-radius: 4px; margin-right: 4px; }
                QTabBar::tab:selected { background: #2563eb; color: white; border-color: #2563eb; }
                QSplitter::handle { background-color: #475569; }
            """
            # Cores específicas de botões funcionais
            btn_unlock_style = "background-color: #d97706; color: white; font-weight: bold; border-radius: 4px; padding: 5px 10px;"
            btn_anon_style = "background-color: #475569; color: white; padding: 8px; border-radius: 4px;"
            btn_qr_style = "background-color: #2563eb; color: white; padding: 8px; border-radius: 4px; font-weight: bold;"
            btn_clear_style = "background-color: #ef4444; color: white; padding: 8px; border-radius: 4px; font-weight: bold;"
            live_log_style = "background: #1e293b; color: #4ade80; font-family: Consolas, monospace; font-size: 12px; border: 1px solid #475569;"

        else:
            # Estilo CLARO (Padrão)
            style = """
                QMainWindow, QWidget { background-color: #f8fafc; color: #1e293b; }
                QLineEdit { background-color: #ffffff; color: #1e293b; border: 1px solid #cbd5e1; padding: 6px; border-radius: 4px; }
                QTextEdit { background-color: #ffffff; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 4px; }
                QGroupBox { border: 1px solid #94a3b8; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #1e293b; }
                QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
                QLabel { color: #1e293b; }
                QPushButton { background-color: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #e2e8f0; }
                QTabBar::tab { background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; padding: 8px 30px 8px 12px; border-radius: 4px; margin-right: 4px; }
                QTabBar::tab:selected { background: #2563eb; color: white; border-color: #2563eb; }
                QSplitter::handle { background-color: #cbd5e1; }
            """
            # Cores específicas
            btn_unlock_style = "background-color: #f59e0b; color: white; font-weight: bold; border-radius: 4px; padding: 5px 10px;"
            btn_anon_style = "background-color: #334155; color: white; padding: 8px; border-radius: 4px;"
            btn_qr_style = "background-color: #2563eb; color: white; padding: 8px; border-radius: 4px; font-weight: bold;"
            btn_clear_style = "background-color: #ef4444; color: white; padding: 8px; border-radius: 4px; font-weight: bold;"
            live_log_style = "background: #1e293b; color: #4ade80; font-family: Consolas, monospace; font-size: 12px;"

        self.setStyleSheet(style)
        
        # Reaplica estilos específicos que não devem ser sobrescritos pelo genérico
        self.btn_open_anon.setStyleSheet(btn_anon_style)
        self.btn_gen_qr.setStyleSheet(btn_qr_style)
        self.btn_clear_qr.setStyleSheet(btn_clear_style)
        self.btn_limpar_busca.setStyleSheet(btn_clear_style)
        self.txt_live.setStyleSheet(live_log_style)
        
        # Ajusta botões do cabeçalho para parecerem com o tema
        btn_conf_color = "#334155" if modo == "dark" else "#f1f5f9"
        btn_conf_border = "#475569" if modo == "dark" else "#cbd5e1"
        header_btn_style = f"""
            QPushButton {{ background-color: {btn_conf_color}; color: {'white' if modo=='dark' else '#334155'}; border: 1px solid {btn_conf_border}; border-radius: 6px; font-size: 20px; }}
            QPushButton:hover {{ border-color: #94a3b8; background-color: {'#475569' if modo=='dark' else '#e2e8f0'}; }}
        """
        self.btn_config.setStyleSheet(header_btn_style)
        self.btn_instrucao.setStyleSheet(header_btn_style)
        self.btn_abrir_camera.setStyleSheet(header_btn_style)
        self.btn_unlock.setStyleSheet(header_btn_style)
        self.btn_upload_excel.setStyleSheet(header_btn_style)
        self.btn_zk_count.setStyleSheet(header_btn_style + "padding: 0 10px; font-size: 14px;")
        self.btn_transferir.setStyleSheet(header_btn_style)
        self.btn_download_img.setStyleSheet(header_btn_style)
        self.btn_back.setStyleSheet(header_btn_style)
        self.btn_forward.setStyleSheet(header_btn_style)
        self.btn_reload.setStyleSheet(header_btn_style)
        self.btn_home.setStyleSheet(header_btn_style)

    # === MÉTODOS DE CONTROLE DO BANCO DE DADOS ===
    def abrir_configuracoes(self):
        """Abre o diálogo de configurações central"""
        dlg = ConfigDialog(self)
        dlg.exec()

    def abrir_instrucoes(self):
        """Abre o diálogo de instruções de cadastramento"""
        dlg = InstrucoesDialog(self)
        dlg.exec()

    def abrir_selecao_arquivo(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Selecionar Banco de Dados", "", "SQLite Database (*.db);;Todos os Arquivos (*)")
        if fname:
            self.conectar_banco(fname)

    def criar_novo_arquivo(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Salvar Novo Banco de Dados", "", "SQLite Database (*.db)")
        if fname:
            self.conectar_banco(fname)

    def carregar_ultimo_banco(self):
        """Verifica se existe um banco salvo nas configurações e tenta carregar"""
        last_db = self.settings.value("last_db_path")
        if last_db and os.path.exists(last_db):
            self.txt_live.append(f"📁 Encontrado banco salvo: {last_db}")
            self.conectar_banco(last_db)
        else:
            self.txt_live.append("⚠️ Nenhum banco anterior encontrado. Configure nas opções.")
            # self.abrir_configuracoes() # Opcional: abrir auto

    def conectar_banco(self, path):
        try:
            self.db = DatabaseHandler(path)
            nome_arq = os.path.basename(path)
            self.lbl_status_db.setText(f"✅ Ativo: {nome_arq}")
            self.lbl_status_db.setStyleSheet("color: #10b981; font-weight: bold; margin-bottom: 5px; font-size: 11px;")
            
            # Salva o caminho para a próxima sessão
            self.settings.setValue("last_db_path", path)
            
            self.txt_live.append(f"--- BANCO CONECTADO: {path} ---")
            self.carregar_ultimo_id()
            self.carregar_url_id()
            
        except Exception as e:
            QMessageBox.critical(self, "Erro de Conexão", f"Falha ao conectar ao banco de dados:\n{e}")
            self.settings.remove("last_db_path")

    # === MÉTODOS DE NAVEGAÇÃO ===
    def navegar_voltar(self):
        view = self.web_stack.currentWidget()
        if view: view.back()

    def navegar_avancar(self):
        view = self.web_stack.currentWidget()
        if view: view.forward()

    def recarregar_pagina(self):
        view = self.web_stack.currentWidget()
        if view: view.reload()

    def add_new_tab(self, qurl, title, closable=True, profile=None):
        view = QWebEngineView()
        target_profile = profile if profile else QWebEngineProfile.defaultProfile()
        page = CustomWebPage(target_profile, view, self)
        view.setPage(page)
        
        view.urlChanged.connect(lambda q: self.atualizar_barra_endereco(q, view))
        view.titleChanged.connect(lambda t: self.atualizar_titulo_aba(t, view))
        view.loadFinished.connect(lambda ok: self.on_tab_load_finished(ok, view))
        
        idx = self.web_stack.addWidget(view)
        tab_idx = self.tabs.addTab(title)
        if not closable: 
            self.tabs.setTabButton(tab_idx, QTabBar.ButtonPosition.RightSide, None)
            
        if qurl and not qurl.isEmpty(): 
            view.setUrl(qurl)
            
        self.tabs.setCurrentIndex(tab_idx)
        self.web_stack.setCurrentIndex(idx)
        return view

    def executar_desbloqueio(self):
        view = self.web_stack.currentWidget()
        if not view: return
        js_hack = """
        (function() {
            var disabledEls = document.querySelectorAll('*[disabled], .disabled, .blocked, .locked, [aria-disabled="true"]');
            disabledEls.forEach(el => {
                el.removeAttribute('disabled');
                el.classList.remove('disabled', 'blocked', 'locked');
                el.setAttribute('aria-disabled', 'false');
                el.style.pointerEvents = 'auto';
                el.style.opacity = '1';
                el.style.cursor = 'pointer';
            });
        })();
        """
        view.page().runJavaScript(js_hack)

    def ir_para_url(self):
        url_texto = self.address_bar.text().strip()
        if not url_texto: return
        if url_texto != "about:blank" and not url_texto.startswith("http") and not url_texto.startswith("about:"):
            url_texto = "https://" + url_texto
        view = self.web_stack.currentWidget()
        if view: view.setUrl(QUrl(url_texto))

    def ir_para_home(self):
        view = self.web_stack.currentWidget()
        if view:
            idx = self.web_stack.currentIndex()
            titulo = self.tabs.tabText(idx)
            if "ZK Bio" in titulo:
                view.setUrl(QUrl(f"{ZK_SERVER}/bioLogin.do"))
            elif view.page().profile() == self.profile_anonimo:
                view.setUrl(QUrl("https://www.google.com"))
            else:
                view.setUrl(QUrl("https://portaria-global.governarti.com.br/visita/"))

    def mudar_aba(self, index):
        if index >= 0:
            self.web_stack.setCurrentIndex(index)
            view = self.web_stack.currentWidget()
            if view:
                url_str = view.url().toString()
                self.address_bar.setText("" if url_str == "about:blank" else url_str)

            # Recolher menu na aba ZK Bio
            titulo = self.tabs.tabText(index)
            if "ZK Bio" in titulo:
                self.painel_lateral.hide()
            else:
                self.painel_lateral.show()

    def update_zk_count(self):
        db_file = "zk_cache.db"
        count = 0
        if os.path.exists(db_file):
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM zk_records")
                count = cursor.fetchone()[0]
                conn.close()
            except: pass
        self.btn_zk_count.setText(f"{count} registros no Zk Bio")

    def importar_excel_zk(self):
        # Abre como diálogo apenas para importação se necessário, ou usa o widget integrado
        self.container_pesquisa_zk.import_excel()

    def abrir_dialogo_excel(self):
        if self.container_pesquisa_zk.isVisible():
            self.container_pesquisa_zk.hide()
            self.stack_central.setCurrentIndex(0)
        else:
            self.container_pesquisa_zk.show()
            self.stack_central.setCurrentIndex(1)

    def fechar_aba(self, index):
        titulo = self.tabs.tabText(index)
        if "Portaria Virtual" in titulo or "anônima" in titulo.lower() or "ZK Bio" in titulo: return
        widget = self.web_stack.widget(index)
        if widget:
            self.web_stack.removeWidget(widget)
            widget.deleteLater()
        self.tabs.removeTab(index)

    def atualizar_titulo_aba(self, titulo, view):
        index = self.web_stack.indexOf(view)
        if index != -1:
            current_text = self.tabs.tabText(index)
            if "Portaria Virtual" in current_text or "anônima" in current_text.lower() or "ZK Bio" in current_text: return
            display_title = (titulo[:12] + "...") if len(titulo) > 12 else titulo
            self.tabs.setTabText(index, display_title)

    def atualizar_barra_endereco(self, qurl, view):
        if view == self.web_stack.currentWidget():
            url_str = qurl.toString()
            self.address_bar.setText("" if url_str == "about:blank" else url_str)

    def configurar_navegadores(self):
        s_worker = self.view_worker.settings()
        s_worker.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, False)
        s_worker.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

    def carregar_ultimo_id(self):
        if not self.db: return
        maior = self.db.get_maior_id_salvo()
        if maior > 0: 
            self.id_atual = maior + 1
            self.txt_live.append(f"🔄 Retomando captura a partir do ID: {self.id_atual}")
        else:
            self.txt_live.append("✨ Banco vazio/novo. Começando do ID 1.")
            self.id_atual = 1

    def carregar_url_id(self):
        if not self.rodando or not self.db: return
        url = f"https://portaria-global.governarti.com.br/visita/{self.id_atual}/detalhes?t={datetime.datetime.now().timestamp()}"
        self.view_worker.setUrl(QUrl(url))

    def injetar_login(self, browser_view):
        if browser_view.page().profile() == self.profile_anonimo: return
        url_atual = browser_view.url().toString()
        if "portaria-global.governarti.com.br/login" in url_atual:
            js_login = f"document.querySelectorAll('input').forEach(i => {{ if(i.type=='text') i.value='{self.creds['portaria_user']}'; if(i.type=='password') i.value='{self.creds['portaria_pass']}'; }});"
            browser_view.page().runJavaScript(js_login)
        elif "bioLogin.do" in url_atual:
            js_login_zk = f"""
                var userField = document.getElementById('username');
                var passField = document.getElementById('password');
                if (userField) userField.value = '{self.creds['zk_user']}';
                if (passField) passField.value = '{self.creds['zk_pass']}';
            """
            browser_view.page().runJavaScript(js_login_zk)

    def on_tab_load_finished(self, ok, view):
        self.injetar_login(view)

    def on_worker_load_finished(self, ok):
        self.injetar_login(self.view_worker)
        if self.rodando and self.db: QTimer.singleShot(800, self.extrair_e_validar)

    def extrair_e_validar(self):
        self.view_worker.page().runJavaScript("document.body.innerText;", self.callback_validacao)

    def callback_validacao(self, conteudo):
        if not self.rodando or not self.db: return
        if not conteudo or "entrar" in conteudo.lower()[:300]:
            self.timer_retry.start(3000)
            return

        nome_str, cpf_str, horario_str = self.db.extrair_dados(conteudo)
        dados_encontrados = (nome_str != "Desconhecido" or cpf_str != "N/A") and "não encontrada" not in conteudo.lower()

        if dados_encontrados:
            agora = datetime.datetime.now().strftime('%H:%M')
            self.db.salvar_visita(self.id_atual, nome_str, cpf_str, horario_str, conteudo, self.view_worker.url().toString())

            msg_log = f"ID {self.id_atual} registrado às {agora}: {nome_str}"
            self.txt_live.append(msg_log)

            # Exibe Notificação Toast
            self.active_toast = NotificationToast("Novo convite!", self)
            self.active_toast.apply_toast_theme(self.settings.value("theme", "light"))
            self.active_toast.show_notification()

            self.id_atual += 1
            QTimer.singleShot(500, self.carregar_url_id)
        else:
            self.timer_retry.start(10000)

    def realizar_busca_local(self):
        self.timer_busca.start(300)

    def executar_busca_local(self):
        termo_raw = self.input_busca.text().strip()
        self.container_pesquisa_zk.filter_and_render(termo_raw)

        if not self.db: return
        termo = termo_raw.lower()
        if not termo: 
            self.txt_res_busca.clear()
            return
        termos = termo.split()
        dados = self.db.buscar_por_filtro(termos)
        html = ""
        hoje = datetime.date.today()
        # Define cor do texto baseada no tema
        text_color = "#e2e8f0" if self.settings.value("theme") == "dark" else "#1e293b"
        card_bg = "#1e293b" if self.settings.value("theme") == "dark" else "#ffffff"
        border_color = "#475569" if self.settings.value("theme") == "dark" else "#cbd5e1"
        
        for vid, nome, cpf, horario in dados:
            cor_validade = "green"
            if horario and horario != "N/A":
                try:
                    partes = horario.split(" - ")
                    if len(partes) == 2:
                        data_fim = datetime.datetime.strptime(partes[1].strip(), "%d/%m/%Y").date()
                        if data_fim < hoje: cor_validade = "red"
                except: pass
            
            html += f"""
            <div style='background-color: {card_bg}; border: 1px solid {border_color}; border-bottom: 3px solid {border_color}; border-radius: 8px; padding: 12px; margin-bottom: 8px;'>
                <div style='color: {text_color}; font-size: 14px;'>
                    <a href="{vid}" style="text-decoration: none; color: inherit;">
                        <b style='color: #2563eb;'>ID {vid}:</b> <span style='color: #ffffff;'>{nome}</span><br>
                        <span style='color: #64748b; font-size: 12px;'>CPF / ID: {cpf}</span><br>
                        <span style='color: #64748b; font-size: 12px;'><b>Validade:</b> <span style='color: {cor_validade}; font-weight: bold;'>{horario}</span></span>
                    </a>
                </div>
            </div>
            """
        self.txt_res_busca.setHtml(html)

    def abrir_link_resultado(self, url_qurl):
        url_str = url_qurl.toString()
        if url_str.startswith("transfer:"):
            visita_id = url_str.split(":")[1]
            self.iniciar_transferencia(visita_id)
            return

        visita_id = url_str
        self.input_transfer_id.setText(visita_id)
        link_final = f"https://portaria-global.governarti.com.br/visita/{visita_id}/detalhes"
        for i in range(self.tabs.count()):
            if "Portaria Virtual" in self.tabs.tabText(i):
                self.tabs.setCurrentIndex(i)
                view = self.web_stack.widget(i)
                if view: view.setUrl(QUrl(link_final))
                return
        self.add_new_tab(QUrl(link_final), f"ID {visita_id}")

    def extrair_url_qr(self):
        texto = self.txt_qr_input.toPlainText()
        match = re.search(r'https?://[^\s]+', texto)
        if match: return match.group(0).rstrip('.')
        return None

    def abrir_qr_na_anonima(self):
        url = self.extrair_url_qr()
        if not url:
            QMessageBox.warning(self, "Aviso", "Nenhuma URL encontrada na mensagem.")
            return
        for i in range(self.tabs.count()):
            if "anônima" in self.tabs.tabText(i).lower():
                self.tabs.setCurrentIndex(i)
                view = self.web_stack.widget(i)
                if view: view.setUrl(QUrl(url))
                return
        self.add_new_tab(QUrl(url), "Guia anônima", closable=False, profile=self.profile_anonimo)

    def mostrar_qr_code(self):
        url = self.extrair_url_qr()
        if not url:
            QMessageBox.warning(self, "Aviso", "Nenhuma URL encontrada na mensagem.")
            return
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(url)
            qr.make(fit=True)
            img_pil = qr.make_image(fill_color="black", back_color="white")
            actual_image = img_pil._img
            qimg = ImageQt(actual_image)
            pixmap = QPixmap.fromImage(qimg)
            dlg = QRDialog(pixmap, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao gerar QR Code: {str(e)}")

    def abrir_camera(self):
        """Abre o diálogo de captura de foto"""
        cameras = QMediaDevices.videoInputs()
        if not cameras:
            QMessageBox.warning(self, "Câmera não encontrada", "Nenhum dispositivo de vídeo foi detectado no sistema.")
            return

        # Tenta evitar a câmera integrada
        camera_selecionada = cameras[0]
        if len(cameras) > 1:
            # Primeiro procura por câmeras que pareçam externas
            for cam in cameras:
                desc = cam.description().lower()
                if "usb" in desc or "external" in desc:
                    camera_selecionada = cam
                    break

            # Se não achou por palavra-chave positiva, tenta excluir as que parecem integradas
            if camera_selecionada == cameras[0]:
                for cam in cameras:
                    desc = cam.description().lower()
                    if "integrated" not in desc and "built-in" not in desc and "notebook" not in desc:
                        camera_selecionada = cam
                        break

        dlg = CameraDialog(self, camera_device=camera_selecionada)
        dlg.exec()

    def ativar_modo_download_imagem(self):
        view = self.web_stack.currentWidget()
        if not view: return

        self.txt_live.append("🎯 [Imagem] Clique em uma imagem para baixar...")

        js_hook = """
        (function() {
            window.__last_captured_img = null;
            window.__download_img_cancel = false;

            var style = document.createElement('style');
            style.id = 'img-selector-style';
            style.innerHTML = 'img { cursor: crosshair !important; outline: 2px solid #2563eb !important; }';
            document.head.appendChild(style);

            function onClick(e) {
                var el = e.target;
                if (el.tagName === 'IMG') {
                    window.__last_captured_img = el.src;
                    cleanup();
                } else {
                    window.__download_img_cancel = true;
                    cleanup();
                }
                e.preventDefault();
                e.stopPropagation();
            }

            function cleanup() {
                document.removeEventListener('click', onClick, true);
                var s = document.getElementById('img-selector-style');
                if (s) s.remove();
            }

            document.addEventListener('click', onClick, true);
        })();
        """
        view.page().runJavaScript(js_hook)
        self.timer_download_img.start(500)

    def verificar_imagem_capturada(self):
        view = self.web_stack.currentWidget()
        if not view:
            self.timer_download_img.stop()
            return

        js_check = "({url: window.__last_captured_img, cancel: window.__download_img_cancel})"
        view.page().runJavaScript(js_check, self.processar_imagem_capturada)

    def processar_imagem_capturada(self, result):
        if not result: return

        url = result.get('url')
        cancel = result.get('cancel')

        if url or cancel:
            self.timer_download_img.stop()
            if url:
                self.baixar_imagem(url)
            else:
                self.txt_live.append("❌ [Imagem] Cancelado (clicou fora de uma imagem).")

    def baixar_imagem(self, url_data):
        try:
            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
            agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"imagem_baixada_{agora}.jpg"
            filepath = os.path.join(downloads_path, filename)

            if url_data.startswith("data:image"):
                # Handle Data URI
                header, encoded = url_data.split(",", 1)
                ext = header.split(";")[0].split("/")[1]
                filename = f"imagem_baixada_{agora}.{ext}"
                filepath = os.path.join(downloads_path, filename)

                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(encoded))
                self.txt_live.append(f"✅ [Imagem] Salva como Data URI: {filename}")
            else:
                # Handle URL
                response = requests.get(url_data, verify=False, timeout=10)
                if response.status_code == 200:
                    # Tenta descobrir a extensão correta
                    content_type = response.headers.get('content-type', '')
                    if 'png' in content_type: filename = filename.replace('.jpg', '.png')
                    elif 'webp' in content_type: filename = filename.replace('.jpg', '.webp')

                    filepath = os.path.join(downloads_path, filename)
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    self.txt_live.append(f"✅ [Imagem] Baixada com sucesso: {filename}")
                else:
                    self.txt_live.append(f"❌ [Imagem] Erro HTTP {response.status_code}")
                    return

            # Notifica o usuário
            self.active_toast = NotificationToast(f"Imagem salva!\n{filename}", self)
            self.active_toast.apply_toast_theme(self.settings.value("theme", "light"))
            self.active_toast.show_notification()

        except Exception as e:
            self.txt_live.append(f"❌ [Imagem] Erro: {str(e)}")

    def iniciar_transferencia(self, id_convite=None):
        if not id_convite:
            id_convite = self.input_transfer_id.text().strip()

        if not id_convite:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("ID não selecionado")
            msg_box.setText("Selecione um ID no banco de dados")
            btn_ok = msg_box.addButton("Ok", QMessageBox.ButtonRole.AcceptRole)
            btn_manual = msg_box.addButton("Inserir manualmente", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = msg_box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()

            if msg_box.clickedButton() == btn_manual:
                id_novo, ok = QInputDialog.getText(self, "Inserir ID", "Digite o ID de convite:")
                if ok and id_novo.strip():
                    return self.iniciar_transferencia(id_novo.strip())
            return

        # Busca o nome no banco para a confirmação
        nome_visitante = None
        if self.db:
            nome_visitante = self.db.buscar_por_id(id_convite)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirmar Transferência")
        if nome_visitante:
            msg_box.setText(f"Deseja transferir os dados de {nome_visitante} Para o ZKBio?")
        else:
            msg_box.setText(f"Deseja transferir os dados do ID {id_convite} Para o ZKBio?")

        btn_sim = msg_box.addButton("Sim", QMessageBox.ButtonRole.YesRole)
        btn_nao = msg_box.addButton("Não", QMessageBox.ButtonRole.NoRole)
        btn_manual = msg_box.addButton("Inserir manualmente", QMessageBox.ButtonRole.ActionRole)
        msg_box.exec()

        if msg_box.clickedButton() == btn_manual:
            id_novo, ok = QInputDialog.getText(self, "Inserir ID", "Digite o ID de convite:")
            if ok and id_novo.strip():
                return self.iniciar_transferencia(id_novo.strip())
            return
        elif msg_box.clickedButton() != btn_sim:
            return

        self.btn_transferir.setEnabled(False)
        self.btn_transferir.setText("⏳")

        self.transfer_thread = TransferThread(id_convite, self.creds)
        self.transfer_thread.log.connect(lambda msg: self.txt_live.append(f"🤖 [Transfer] {msg}"))
        self.transfer_thread.success.connect(self.on_transfer_success)
        self.transfer_thread.error.connect(self.on_transfer_error)
        self.transfer_thread.finished.connect(lambda: self.btn_transferir.setEnabled(True))
        self.transfer_thread.finished.connect(lambda: self.btn_transferir.setText("🚀"))
        self.transfer_thread.start()

    def on_transfer_success(self, msg):
        self.txt_live.append(f"✅ Transferência concluída: {msg.splitlines()[0]}")
        QMessageBox.information(self, "Sucesso", msg)

    def on_transfer_error(self, err):
        self.txt_live.append(f"❌ Erro na transferência: {err}")
        QMessageBox.critical(self, "Erro na Transferência", f"Falha: {err}")

    def closeEvent(self, event):
        if hasattr(self, 'transfer_thread') and self.transfer_thread.isRunning():
            self.transfer_thread.stop()
            self.transfer_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SmartPortariaScanner()
    win.show()
    sys.exit(app.exec())
