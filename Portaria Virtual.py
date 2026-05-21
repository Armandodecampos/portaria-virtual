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
import urllib.parse
import base64
import json

# --- BLOCO DE PROTEÇÃO DE IMPORTAÇÃO ---
try:
    from PyQt6.QtCore import (
        Qt, QUrl, QTimer, QSettings, QSize, pyqtSignal, QMimeData,
        QPropertyAnimation, QEasingCurve, QPoint, QThread, QEvent, QObject
    )
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLineEdit, QPushButton, QLabel, QSplitter, QTextEdit, QTextBrowser, QGroupBox,
        QStackedWidget, QTabBar, QMessageBox, QDialog, QFileDialog, QFrame,
        QRadioButton, QButtonGroup, QInputDialog, QSizePolicy, QScrollArea, QCheckBox,
        QListWidget, QListWidgetItem
    )
    from PyQt6.QtGui import QPixmap, QFont, QIcon, QAction, QImage, QFontMetrics
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
        elif mode == "sepia":
            bg_color = "#3b2a1a"
            text_color = "#f4ecd8"
            border_color = "#554433"
            close_hover = "#2d1f12"
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
        theme = self.parent_window.settings.value("theme", "light")
        if theme == "dark":
            border_color = "#475569"
        elif theme == "sepia":
            border_color = "#554433"
        else:
            border_color = "#cbd5e1"

        self.setStyleSheet(f"""
            QDialog {{ font-size: 14px; }}
            QGroupBox {{ font-weight: bold; border: 1px solid {border_color}; border-radius: 6px; margin-top: 10px; padding-top: 15px; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }}
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
        self.rb_sepia = QRadioButton("Modo Sepia")
        
        # Grupo lógico
        self.bg_theme = QButtonGroup(self)
        self.bg_theme.addButton(self.rb_claro, 1)
        self.bg_theme.addButton(self.rb_escuro, 2)
        self.bg_theme.addButton(self.rb_sepia, 3)
        
        # Define seleção atual
        current_theme = self.parent_window.settings.value("theme", "light")
        if current_theme == "dark":
            self.rb_escuro.setChecked(True)
        elif current_theme == "sepia":
            self.rb_sepia.setChecked(True)
        else:
            self.rb_claro.setChecked(True)
            
        self.bg_theme.idClicked.connect(self.trocar_tema)
        
        lay_theme.addWidget(self.rb_claro)
        lay_theme.addWidget(self.rb_escuro)
        lay_theme.addWidget(self.rb_sepia)
        layout.addWidget(gb_theme)

        # === SEÇÃO MONITORAMENTO ===
        gb_mon = QGroupBox("Captura Automática")
        lay_mon = QHBoxLayout(gb_mon)
        lay_mon.addWidget(QLabel("Próximo ID:"))
        self.edit_next_id = QLineEdit(str(self.parent_window.id_atual))
        self.edit_next_id.setPlaceholderText("Apenas números")
        lay_mon.addWidget(self.edit_next_id)
        btn_set_id = QPushButton("Definir")
        btn_set_id.setStyleSheet("background-color: #3b82f6; color: white; padding: 4px 10px; font-weight: bold;")
        btn_set_id.clicked.connect(self.acao_definir_id)
        lay_mon.addWidget(btn_set_id)
        layout.addWidget(gb_mon)

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
        if id == 2:
            modo = "dark"
        elif id == 3:
            modo = "sepia"
        else:
            modo = "light"
        self.parent_window.aplicar_tema(modo)

    def acao_definir_id(self):
        try:
            val = self.edit_next_id.text().strip()
            if not val or not val.isdigit():
                raise ValueError("ID Inválido")

            novo_id = int(val)
            self.parent_window.id_atual = novo_id
            self.parent_window.txt_live.append(f"🎯 [Config] Monitoramento alterado para ID: {novo_id}")
            self.parent_window.reiniciar_monitores()
            QMessageBox.information(self, "Sucesso", f"Próximo ID definido para {novo_id}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", "Insira um número de ID válido.")

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
        elif theme == "sepia":
            self.setStyleSheet("background-color: #2d1f12; color: #f4ecd8;")
            link_color = "#a67c52"
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

def render_zk_card(item, card_bg, card_border, sub_text_color, accent_color="#3b82f6"):
    """
    Função utilitária para renderizar o card de um registro do ZK Bio.
    """
    copy_btn = f"<a href='copy:{{}}' style='text-decoration: none; color: {accent_color}; font-size: 10px; margin-left: 5px;'>[Copiar]</a>"

    # Cálculo do Código Ifood (últimos 4 dígitos do telefone)
    ifood_code = "-"
    if item['celular'] != "-" and len(re.sub(r'\D', '', item['celular'])) >= 4:
        ifood_code = re.sub(r'\D', '', item['celular'])[-4:]

    html = f"""
    <div style='background-color: {card_bg}; border: 1px solid {card_border}; border-left: 5px solid {accent_color}; border-radius: 10px; padding: 16px; margin-bottom: 12px;'>
        <span style='font-size: 13px; color: {sub_text_color};'><b>Nome:</b> {item['nome']} {item['sobrenome']} {copy_btn.format(urllib.parse.quote(item['nome'] + ' ' + item['sobrenome']))}</span>
    """

    if item['id'] != "-":
        html += f"<br><span style='font-size: 13px; color: {sub_text_color};'><b>Documento:</b> {item['id']} {copy_btn.format(urllib.parse.quote(item['id']))}</span>"

    if item['email'] != "-":
        html += f"<br><span style='font-size: 13px; color: {sub_text_color};'><b>Email:</b> {item['email']} {copy_btn.format(urllib.parse.quote(item['email']))}</span>"

    if item['celular'] != "-":
        html += f"<br><span style='font-size: 13px; color: {sub_text_color};'><b>Telefone:</b> {item['celular']} {copy_btn.format(urllib.parse.quote(item['celular']))}</span>"

    html += f"<br><span style='font-size: 13px; color: {sub_text_color};'><b>ID:</b> {item['cartao']} {copy_btn.format(urllib.parse.quote(item['cartao']))}</span>"

    if ifood_code != "-":
        html += f"<br><span style='font-size: 13px; color: #10b981; font-weight: bold;'>Código Ifood: {ifood_code} {copy_btn.format(urllib.parse.quote(ifood_code))}</span>"

    html += "</div>"
    return html

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
        return render_zk_card(item, self.td['card_bg'], self.td['card_border'], self.td['sub_text_color'], self.td.get('accent_color', '#3b82f6'))

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
            query = "SELECT id, nome, sobrenome, dept, celular, cartao, email, data_upload " + base_query + " ORDER BY dept, nome LIMIT 300"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            html_parts = ["<div style='font-family: sans-serif;'>"]

            current_dept = None
            for r in rows:
                item_data = {"id": r[0], "nome": r[1], "sobrenome": r[2], "dept": r[3], "celular": r[4], "cartao": r[5], "email": r[6], "data_upload": r[7]}
                if item_data["dept"] != current_dept:
                    current_dept = item_data["dept"]
                    accent = self.td.get('accent_color', '#3b82f6')
                    html_parts.append(f"""
                        <div style='background-color: transparent; color: {accent}; padding: 6px 12px; border-radius: 6px;
                                    border-bottom: 2px solid {accent}; margin-top: 20px; margin-bottom: 12px; font-weight: bold; font-size: 16px;'>
                            📂 {current_dept}
                        </div>
                    """)
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

    def aplicar_tema(self, modo):
        self.theme = modo
        if modo == "dark":
            self.setStyleSheet("background-color: #0f172a; color: #e2e8f0;")
            self.card_bg = "#1e293b"
            self.card_border = "#334155"
            self.text_color = "#f8fafc"
            self.sub_text_color = "#94a3b8"
            self.accent_color = "#3b82f6"
        elif modo == "sepia":
            self.setStyleSheet("background-color: #2d1f12; color: #f4ecd8;")
            self.card_bg = "#3b2a1a"
            self.card_border = "#554433"
            self.text_color = "#f4ecd8"
            self.sub_text_color = "#d4c3a1"
            self.accent_color = "#d9975d"
        else:
            self.setStyleSheet("background-color: #f8fafc; color: #1e293b;")
            self.card_bg = "#ffffff"
            self.card_border = "#cbd5e1"
            self.text_color = "#1e293b"
            self.sub_text_color = "#64748b"
            self.accent_color = "#3b82f6"

        if hasattr(self, 'input_search'):
            self.input_search.setStyleSheet(f"border-radius: 20px; padding: 10px 15px; border: 2px solid {self.card_border};")

        if hasattr(self, 'lbl_title'):
            self.lbl_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.accent_color};")

        if hasattr(self, 'btn_upload'):
            self.btn_upload.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.accent_color};
                    color: white;
                    font-weight: bold;
                    padding: 10px 15px;
                    border-radius: 5px;
                }}
                QPushButton:hover {{ background-color: {self.card_border}; }}
            """)

    def setup_ui(self):
        self.aplicar_tema(self.theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Cabeçalho: Selecionar Arquivo
        header_lay = QHBoxLayout()

        # Container para o título e o botão de upload
        upload_container = QVBoxLayout()
        upload_container.setSpacing(2)
        self.lbl_title = QLabel("Registros ZK Bio")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #3b82f6;")
        upload_container.addWidget(self.lbl_title)

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
        upload_container.addWidget(self.btn_upload)
        header_lay.addLayout(upload_container)

        self.lbl_file_name = QLabel("")
        self.lbl_file_name.setStyleSheet("""
            QLabel {
                background-color: #1e293b;
                color: #94a3b8;
                padding: 5px 12px;
                border-radius: 12px;
                font-size: 11px;
                border: 1px solid #334155;
            }
        """)
        header_lay.addWidget(self.lbl_file_name, alignment=Qt.AlignmentFlag.AlignBottom)
        header_lay.addStretch()

        # Botão Fechar no cabeçalho
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.clicked.connect(self.fechar_ou_ocultar)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton:hover { background-color: #dc2626; }
        """)
        header_lay.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_lay)

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
        self.aplicar_tema(self.theme) # Reaplica para garantir estilos dinâmicos

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
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self.handle_copy_link)
        self.browser.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.browser)

    def handle_copy_link(self, qurl):
        url_str = qurl.toString()
        if url_str.startswith("copy:"):
            text_to_copy = urllib.parse.unquote(url_str[5:])
            QApplication.clipboard().setText(text_to_copy)
            if self.parent_window:
                self.parent_window.txt_live.append(f"📋 Copiado: {text_to_copy}")

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

            # Recupera a data de upload do cache
            try:
                conn = self.get_db_conn()
                cursor = conn.cursor()
                cursor.execute("SELECT data_upload FROM zk_records LIMIT 1")
                res = cursor.fetchone()
                if res and res[0]:
                    self.update_file_label("Dados do cache", res[0])
                else:
                    self.lbl_file_name.setText("Dados carregados do cache (.db).")
            except:
                self.lbl_file_name.setText("Dados carregados do cache (.db).")

            self.render_department_filters()
            self.filter_and_render()

    def save_to_cache_db(self, new_items, upload_date=None):
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
                    celular TEXT, cartao TEXT, email TEXT, search_text TEXT,
                    data_upload TEXT
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
                        item["celular"], item["cartao"], item["email"], item["search_text"],
                        upload_date
                    ))

            cursor.executemany("INSERT INTO zk_records VALUES (?,?,?,?,?,?,?,?,?)", records)
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

    def update_file_label(self, source_name, timestamp):
        """
        Atualiza o label do arquivo com a lógica de aviso de data desatualizada.
        """
        try:
            # Assume formato DD/MM/YYYY HH:mm
            date_str = timestamp.split()[0]
            current_date_str = datetime.datetime.now().strftime("%d/%m/%Y")

            is_outdated = date_str != current_date_str
            color = "#ef4444" if is_outdated else "#3b82f6"

            html = f"{source_name} <span style='color: {color};'>📅 {timestamp}</span>"
            if is_outdated:
                html += " <span style='color: #ef4444; font-weight: bold;'>Considere fazer o upload do arquivo atualizado.</span>"

            self.lbl_file_name.setText(html)
        except:
            self.lbl_file_name.setText(f"{source_name} 📅 {timestamp}")

    def import_excel(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Selecionar Excel", "", "Excel Files (*.xls *.xlsx)")
        if not fname: return

        try:
            now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            self.update_file_label(f"📂 {os.path.basename(fname)}", now_str)

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

            self.save_to_cache_db(new_items, upload_date=now_str)
            self.render_department_filters()
            self.filter_and_render()

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao importar Excel: {e}")

    def fechar_ou_ocultar(self):
        if self.parent_window:
            self.parent_window.abrir_dialogo_excel()

    def filter_and_render(self, search_text_raw=None):
        if search_text_raw is None:
            search_text_raw = self.input_search.text().strip()
        search_query = self.normalize_text(search_text_raw)

        if not search_query:
            self.browser.clear()
            return

        visible_depts = [dept for dept, cb in self.department_checkboxes.items() if cb.isChecked()]
        if not visible_depts:
            self.browser.clear()
            return

        # Cancela busca anterior se existir
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.terminate()
            self.search_thread.wait()

        theme_data = {
            "card_bg": self.card_bg,
            "card_border": self.card_border,
            "text_color": self.text_color,
            "sub_text_color": self.sub_text_color,
            "accent_color": self.accent_color
        }

        self.search_thread = SearchThread(search_query, visible_depts, theme_data)
        self.search_thread.results_ready.connect(self.on_search_finished)
        self.search_thread.start()

    def on_search_finished(self, html, total_count):
        self.browser.setHtml(html)

    def render_item_card(self, item):
        # Este método agora é usado principalmente para importação imediata,
        # mas a thread tem sua própria versão. Mantemos para consistência.
        return render_zk_card(item, self.card_bg, self.card_border, self.sub_text_color)

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

class RoboCapture(QObject):
    log_signal = pyqtSignal(str)
    new_visit_signal = pyqtSignal(str) # Para notificação

    def __init__(self, name, strategy, db, parent_scanner):
        super().__init__(parent_scanner)
        self.name = name
        self.strategy = strategy # 'sequential' ou 'range'
        self.range_size = 0
        if isinstance(strategy, tuple):
            self.strategy, self.range_size = strategy

        self.db = db
        self.parent_scanner = parent_scanner
        self.id_inicio_ciclo = 0
        self.id_atual_robo = 0
        self.rodando = False

        self.view = QWebEngineView(parent_scanner)
        self.view.setVisible(False)
        # Otimização de recursos: não carregar imagens para os robôs
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, False)
        self.view.loadFinished.connect(self.on_load_finished)

        self.timer_retry = QTimer(self)
        self.timer_retry.setSingleShot(True)
        self.timer_retry.timeout.connect(self.carregar_url)

    def iniciar(self, id_base):
        self.rodando = True
        self.id_inicio_ciclo = id_base
        self.id_atual_robo = id_base
        self.log_signal.emit(f"🤖 {self.name} iniciado no ID: {self.id_atual_robo}")
        self.carregar_url()

    def parar(self):
        self.rodando = False
        self.timer_retry.stop()
        self.view.stop()

    def carregar_url(self):
        if not self.rodando: return

        # Antes de carregar, verifica se o ID já existe no banco (pode ter sido capturado por outro robô)
        if self.db.buscar_por_id(self.id_atual_robo):
            # Se já existe, pula para o próximo
            if self.strategy == 'sequential':
                self.parent_scanner.id_atual = self.id_atual_robo + 1

            self.proximo_id()
            QTimer.singleShot(100, self.carregar_url)
            return

        url = f"https://portaria-global.governarti.com.br/visita/{self.id_atual_robo}/detalhes?t={datetime.datetime.now().timestamp()}"
        self.view.setUrl(QUrl(url))

    def on_load_finished(self, ok):
        if not self.rodando: return
        # Injetar login se necessário (compartilha sessão, mas garante)
        self.parent_scanner.injetar_login(self.view)
        QTimer.singleShot(800, self.extrair_dados)

    def extrair_dados(self):
        if not self.rodando: return
        self.view.page().runJavaScript("document.body.innerText;", self.callback_validacao)

    def callback_validacao(self, conteudo):
        if not self.rodando: return
        if not conteudo or "entrar" in conteudo.lower()[:400]:
            self.timer_retry.start(3000)
            return

        # self.log_signal.emit(f"🤖 {self.name}: Verificando ID {self.id_atual_robo}...")
        nome_str, cpf_str, horario_str = DatabaseHandler.extrair_dados(conteudo)
        dados_encontrados = (nome_str != "Desconhecido" or cpf_str != "N/A") and "não encontrada" not in conteudo.lower()

        if dados_encontrados:
            agora = datetime.datetime.now().strftime('%H:%M')
            if self.db.salvar_visita(self.id_atual_robo, nome_str, cpf_str, horario_str, conteudo, self.view.url().toString()):
                msg_log = f"🤖 {self.name}: ID {self.id_atual_robo} registrado às {agora}: {nome_str}"
                self.log_signal.emit(msg_log)
                self.new_visit_signal.emit(nome_str)

                # Se for Robo 1 (sequential), atualiza o id_atual global
                if self.strategy == 'sequential':
                    self.parent_scanner.id_atual = self.id_atual_robo + 1

            self.proximo_id()
            QTimer.singleShot(500, self.carregar_url)
        else:
            if self.strategy == 'sequential':
                self.timer_retry.start(10000)
            else:
                self.proximo_id()
                QTimer.singleShot(500, self.carregar_url)

    def proximo_id(self):
        if self.strategy == 'sequential':
            self.id_atual_robo += 1
        else:
            self.id_atual_robo += 1
            if self.id_atual_robo > self.id_inicio_ciclo + self.range_size:
                # Reinicia o ciclo a partir do id_atual global
                self.id_inicio_ciclo = self.parent_scanner.id_atual
                self.id_atual_robo = self.id_inicio_ciclo

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

        # Regex mais robusta para Nome (captura até o fim da linha ou delimitadores comuns)
        reg_nome = r"Visitante:\s*([^\n\r\|]+)"
        # Regex para CPF que aceita formatado ou apenas números (11 dígitos)
        reg_cpf = r"(\d{3}\.\d{3}\.\d{3}-\d{2})|(\b\d{11}\b)"
        reg_horario = r"Horário:\s*(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}\s*-\s*(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}"

        m_nome = re.search(reg_nome, conteudo, re.IGNORECASE)
        m_cpf = re.search(reg_cpf, conteudo)
        m_horario = re.search(reg_horario, conteudo)

        raw_nome = m_nome.group(1).strip() if m_nome else "Desconhecido"
        cpf = m_cpf.group(0) if m_cpf else "N/A"
        horario = f"{m_horario.group(1)} - {m_horario.group(2)}" if m_horario else "N/A"

        # Limpeza adicional do nome
        if cpf != "N/A" and cpf in raw_nome:
            raw_nome = raw_nome.replace(cpf, "")

        # Remove labels que podem ter ficado grudados
        labels = ["Telefone", "CPF", "Celular", "Horário", "Empresa", "E-mail"]
        clean_nome = raw_nome
        for label in labels:
            if label in clean_nome:
                clean_nome = clean_nome.split(label)[0]

        clean_nome = clean_nome.strip(" -|")
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
        self.robos = []

        self.profile_anonimo = QWebEngineProfile(self) 
        self.profile_anonimo.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Janela de pesquisa integrada (deve ser criada antes do setup_ui para ser adicionada ao layout)
        self.container_pesquisa_zk = ExcelRecordsWidget(self)
        self.container_pesquisa_zk.hide()

        self.setup_ui()
        self.configurar_navegadores()

        # Filtro de eventos global para fechar container ZK ao clicar fora
        QApplication.instance().installEventFilter(self)

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
        layout_busca.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout_busca.setSpacing(10)
        layout_busca.setContentsMargins(10, 10, 10, 10)
        
        # Botão de Alternância
        self.btn_toggle_busca = QPushButton("🔍 Busca: Todos os dados")
        self.btn_toggle_busca.setStyleSheet("font-weight: bold; padding: 5px;")
        self.btn_toggle_busca.clicked.connect(self.alternar_modo_busca)
        layout_busca.addWidget(self.btn_toggle_busca)

        self.stack_busca = QStackedWidget()
        self.stack_busca.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # Página 0: Busca normal
        container_normal = QWidget()
        lay_normal = QHBoxLayout(container_normal)
        lay_normal.setContentsMargins(0, 0, 0, 0)
        lay_normal.setSpacing(10)

        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Nome ou ID...")
        self.input_busca.textChanged.connect(self.realizar_busca_normal)
        
        self.btn_limpar_busca = QPushButton("Apagar")
        self.btn_limpar_busca.setFixedWidth(70)
        self.btn_limpar_busca.clicked.connect(self.input_busca.clear)

        lay_normal.addWidget(self.input_busca)
        lay_normal.addWidget(self.btn_limpar_busca)
        self.stack_busca.addWidget(container_normal)

        # Página 1: Busca por CPF
        container_cpf = QWidget()
        lay_cpf = QHBoxLayout(container_cpf)
        lay_cpf.setContentsMargins(0, 0, 0, 0)
        lay_cpf.setSpacing(10)

        self.input_busca_cpf = QLineEdit()
        self.input_busca_cpf.setPlaceholderText("CPF (somente números)...")
        self.input_busca_cpf.textChanged.connect(self.realizar_busca_cpf)

        self.btn_limpar_busca_cpf = QPushButton("Apagar")
        self.btn_limpar_busca_cpf.setFixedWidth(70)
        self.btn_limpar_busca_cpf.clicked.connect(self.input_busca_cpf.clear)

        lay_cpf.addWidget(self.input_busca_cpf)
        lay_cpf.addWidget(self.btn_limpar_busca_cpf)
        self.stack_busca.addWidget(container_cpf)

        layout_busca.addWidget(self.stack_busca)
        
        self.txt_res_busca = QTextBrowser()
        self.txt_res_busca.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.txt_res_busca.setOpenExternalLinks(False)
        self.txt_res_busca.setOpenLinks(False)
        self.txt_res_busca.document().setDocumentMargin(0)
        # O estilo base transparente é bom, mas vamos deixar o tema controlar a cor do texto
        self.txt_res_busca.setStyleSheet("border: none; background: transparent; margin: 0; padding: 0;")
        self.txt_res_busca.anchorClicked.connect(self.abrir_link_resultado)
        layout_busca.addWidget(self.txt_res_busca)
        lat.addWidget(group_busca, 3)

        # === GRUPO LOG ===
        group_live = QGroupBox("LOG DO SISTEMA")
        layout_live = QVBoxLayout(group_live)
        layout_live.setContentsMargins(10, 10, 10, 10)
        layout_live.setSpacing(10)
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

        layout_web.addWidget(self.stack_central, 1)
        layout_web.addWidget(self.container_pesquisa_zk)

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

        elif modo == "sepia":
            # Estilo SEPIA (Deep Sepia High Contrast)
            style = """
                QMainWindow, QWidget { background-color: #2d1f12; color: #f4ecd8; }
                QLineEdit { background-color: #3b2a1a; color: #ffffff; border: 1px solid #554433; padding: 6px; border-radius: 4px; }
                QTextEdit { background-color: #3b2a1a; color: #ffffff; border: 1px solid #554433; border-radius: 4px; }
                QGroupBox { border: 1px solid #554433; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #d4c3a1; }
                QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
                QLabel { color: #f4ecd8; }
                QPushButton { background-color: #3b2a1a; color: #f4ecd8; border: 1px solid #554433; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #554433; }
                QTabBar::tab { background: #3b2a1a; color: #d4c3a1; border: 1px solid #554433; padding: 8px 30px 8px 12px; border-radius: 4px; margin-right: 4px; }
                QTabBar::tab:selected { background: #d9975d; color: white; border-color: #d9975d; }
                QSplitter::handle { background-color: #554433; }
            """
            # Cores específicas
            btn_unlock_style = "background-color: #d9975d; color: white; font-weight: bold; border-radius: 4px; padding: 5px 10px;"
            btn_anon_style = "background-color: #554433; color: white; padding: 8px; border-radius: 4px;"
            btn_qr_style = "background-color: #c08b5c; color: white; padding: 8px; border-radius: 4px; font-weight: bold;"
            btn_clear_style = "background-color: #ef4444; color: white; padding: 8px; border-radius: 4px; font-weight: bold;"
            live_log_style = "background: #1a120b; color: #f4ecd8; font-family: Consolas, monospace; font-size: 12px; border: 1px solid #554433;"

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
        self.btn_limpar_busca_cpf.setStyleSheet(btn_clear_style)
        self.btn_toggle_busca.setStyleSheet(btn_qr_style)
        self.txt_live.setStyleSheet(live_log_style)
        
        # Ajusta botões do cabeçalho para parecerem com o tema
        if modo == "dark":
            btn_conf_color = "#334155"
            btn_conf_border = "#475569"
            icon_color = "#94a3b8"
        elif modo == "sepia":
            btn_conf_color = "#3b2a1a"
            btn_conf_border = "#554433"
            icon_color = "#d4c3a1"
        else:
            btn_conf_color = "#f1f5f9"
            btn_conf_border = "#cbd5e1"
            icon_color = "#475569"
        if modo == "dark":
            btn_text_color = "white"
            btn_hover_bg = "#475569"
        elif modo == "sepia":
            btn_text_color = "#f4ecd8"
            btn_hover_bg = "#554433"
        else:
            btn_text_color = "#334155"
            btn_hover_bg = "#e2e8f0"

        header_btn_style = f"""
            QPushButton {{ background-color: {btn_conf_color}; color: {btn_text_color}; border: 1px solid {btn_conf_border}; border-radius: 6px; font-size: 20px; }}
            QPushButton:hover {{ border-color: #94a3b8; background-color: {btn_hover_bg}; }}
        """
        self.btn_config.setStyleSheet(header_btn_style)
        self.btn_instrucao.setStyleSheet(header_btn_style)
        self.btn_abrir_camera.setStyleSheet(header_btn_style)
        self.btn_unlock.setStyleSheet(header_btn_style)
        self.btn_transferir.setStyleSheet(header_btn_style)
        self.btn_download_img.setStyleSheet(header_btn_style)
        self.btn_back.setStyleSheet(header_btn_style)
        self.btn_forward.setStyleSheet(header_btn_style)
        self.btn_reload.setStyleSheet(header_btn_style)
        self.btn_home.setStyleSheet(header_btn_style)

        # Propaga o tema para o container ZK
        self.container_pesquisa_zk.aplicar_tema(modo)

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

    def importar_excel_zk(self):
        # Abre como diálogo apenas para importação se necessário, ou usa o widget integrado
        self.container_pesquisa_zk.import_excel()

    def abrir_dialogo_excel(self):
        if self.container_pesquisa_zk.isVisible():
            self.container_pesquisa_zk.hide()
        else:
            self.container_pesquisa_zk.setFixedHeight(self.height() // 2)
            self.container_pesquisa_zk.show()

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
        # Configurações globais se necessário
        pass

    def carregar_ultimo_id(self):
        if not self.db: return

        maior = self.db.get_maior_id_salvo()
        if maior > 0: 
            self.id_atual = maior + 1
            self.txt_live.append(f"🔄 Retomando captura a partir do ID: {self.id_atual}")
        else:
            self.txt_live.append("✨ Banco vazio/novo. Começando do ID 1.")
            self.id_atual = 1

        self.reiniciar_monitores()

    def reiniciar_monitores(self):
        if not self.db: return

        # Para robôs existentes
        for robo in self.robos:
            try: robo.parar()
            except: pass
        self.robos = []

        # Inicializa os 4 robôs
        configs_robos = [
            ("Robo 1", "sequential", 0),
            ("Robo 2", ("range", 50), 2000),
            ("Robo 3", ("range", 100), 4000),
            ("Robo 4", ("range", 1000), 6000),
        ]

        for name, strategy, delay in configs_robos:
            robo = RoboCapture(name, strategy, self.db, self)
            robo.log_signal.connect(lambda msg: self.txt_live.append(msg))
            robo.new_visit_signal.connect(self.exibir_notificacao)
            self.robos.append(robo)
            if delay == 0:
                robo.iniciar(self.id_atual)
            else:
                QTimer.singleShot(delay, lambda r=robo: r.iniciar(self.id_atual))

    def injetar_login(self, browser_view):
        if browser_view.page().profile() == self.profile_anonimo: return
        url_atual = browser_view.url().toString()
        if "portaria-global.governarti.com.br/login" in url_atual:
            js_login = f"""
                var inputs = document.querySelectorAll('input');
                var form = document.querySelector('form');
                inputs.forEach(i => {{
                    if(i.type=='text') i.value='{self.creds['portaria_user']}';
                    if(i.type=='password') i.value='{self.creds['portaria_pass']}';
                }});
                if(form) form.submit();
            """
            browser_view.page().runJavaScript(js_login)
        elif "bioLogin.do" in url_atual:
            js_login_zk = f"""
                var userField = document.getElementById('username');
                var passField = document.getElementById('password');
                var btn = document.querySelector('input[type="button"]') || document.querySelector('button');
                if (userField) userField.value = '{self.creds['zk_user']}';
                if (passField) passField.value = '{self.creds['zk_pass']}';
                if (btn) btn.click();
            """
            browser_view.page().runJavaScript(js_login_zk)

    def on_tab_load_finished(self, ok, view):
        self.injetar_login(view)

    def exibir_notificacao(self, nome_visitante):
        # Exibe Notificação Toast de forma segura
        self.active_toast = NotificationToast(f"Novo convite: {nome_visitante}", self)
        self.active_toast.apply_toast_theme(self.settings.value("theme", "light"))
        self.active_toast.show_notification()

    def formatar_cpf(self, texto):
        """Formata uma string numérica para o padrão 000.000.000-00"""
        numeros = re.sub(r'\D', '', texto)
        if len(numeros) > 11:
            numeros = numeros[:11]

        if len(numeros) <= 3:
            return numeros
        elif len(numeros) <= 6:
            return f"{numeros[:3]}.{numeros[3:]}"
        elif len(numeros) <= 9:
            return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:]}"
        else:
            return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"

    def realizar_busca_normal(self):
        if self.input_busca.text():
            self.input_busca_cpf.blockSignals(True)
            self.input_busca_cpf.clear()
            self.input_busca_cpf.blockSignals(False)
        self.timer_busca.start(300)

    def realizar_busca_cpf(self):
        if self.input_busca_cpf.text():
            self.input_busca.blockSignals(True)
            self.input_busca.clear()
            self.input_busca.blockSignals(False)
        self.timer_busca.start(300)

    def alternar_modo_busca(self):
        novo_idx = 1 if self.stack_busca.currentIndex() == 0 else 0
        self.stack_busca.setCurrentIndex(novo_idx)

        if novo_idx == 0:
            self.btn_toggle_busca.setText("🔍 Busca: Todos os dados")
            self.input_busca_cpf.clear()
        else:
            self.btn_toggle_busca.setText("🔍 Busca: CPF")
            self.input_busca.clear()

        self.txt_res_busca.clear()
        self.container_pesquisa_zk.browser.clear()

    def realizar_busca_local(self):
        self.timer_busca.start(300)

    def executar_busca_local(self):
        # Verifica qual modo de busca está ativo no stack
        if self.stack_busca.currentIndex() == 1:
            # MODO CPF
            cpf_raw = self.input_busca_cpf.text().strip()
            # Para o Relatório ZK Bio (ExcelRecordsWidget), busca-se sem pontos
            self.container_pesquisa_zk.filter_and_render(re.sub(r'\D', '', cpf_raw))
            termo_db = self.formatar_cpf(cpf_raw)
            termo_para_check = cpf_raw
        else:
            # MODO TODOS OS DADOS
            termo_normal = self.input_busca.text().strip()
            self.container_pesquisa_zk.filter_and_render(termo_normal)
            termo_db = termo_normal
            termo_para_check = termo_normal

        if termo_para_check and not self.container_pesquisa_zk.isVisible():
            self.abrir_dialogo_excel()

        if not self.db: return

        if not termo_db:
            self.txt_res_busca.clear()
            return

        termos = termo_db.lower().split()
        dados = self.db.buscar_por_filtro(termos)
        html = ""
        hoje = datetime.date.today()
        # Define cor do texto baseada no tema
        current_theme = self.settings.value("theme")
        if current_theme == "dark":
            text_color = "#e2e8f0"
            card_bg = "#1e293b"
            border_color = "#475569"
            accent_color = "#3b82f6"
            name_color = "#ffffff"
            subtext_color = "#94a3b8"
        elif current_theme == "sepia":
            text_color = "#f4ecd8"
            card_bg = "#3b2a1a"
            border_color = "#554433"
            accent_color = "#d9975d"
            name_color = "#ffffff"
            subtext_color = "#d4c3a1"
        else:
            text_color = "#1e293b"
            card_bg = "#ffffff"
            border_color = "#cbd5e1"
            accent_color = "#2563eb"
            name_color = "#1e293b"
            subtext_color = "#64748b"
        
        for vid, nome, cpf, horario in dados:
            cor_validade = "#10b981" if current_theme in ["dark", "sepia"] else "green"
            if horario and horario != "N/A":
                try:
                    partes = horario.split(" - ")
                    if len(partes) == 2:
                        data_fim = datetime.datetime.strptime(partes[1].strip(), "%d/%m/%Y").date()
                        if data_fim < hoje: cor_validade = "#ef4444"
                except: pass
            
            html += f"""
            <div style='background-color: {card_bg}; border: 1px solid {border_color}; border-bottom: 3px solid {border_color}; border-radius: 8px; padding: 12px; margin-bottom: 0px;'>
                <div style='color: {text_color}; font-size: 14px;'>
                    <a href="{vid}" style="text-decoration: none; color: inherit;">
                        <b style='color: {accent_color};'>ID {vid}:</b> <span style='color: {name_color}; font-weight: bold;'>{nome}</span><br>
                        <span style='color: {subtext_color}; font-size: 12px;'>CPF / ID: {cpf}</span><br>
                        <span style='color: {subtext_color}; font-size: 12px;'><b>Validade:</b> <span style='color: {cor_validade}; font-weight: bold;'>{horario}</span></span>
                    </a>
                </div>
            </div>
            """
        self.txt_res_busca.setHtml(html)

    def abrir_link_resultado(self, url_qurl):
        url_str = url_qurl.toString()
        if url_str.startswith("copy:"):
            text_to_copy = urllib.parse.unquote(url_str[5:])
            QApplication.clipboard().setText(text_to_copy)
            self.txt_live.append(f"📋 Copiado: {text_to_copy}")
            return

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

    def resizeEvent(self, event):
        if hasattr(self, 'container_pesquisa_zk') and self.container_pesquisa_zk.isVisible():
            self.container_pesquisa_zk.setFixedHeight(self.height() // 2)
        super().resizeEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if hasattr(self, 'container_pesquisa_zk') and self.container_pesquisa_zk.isVisible():
                # Obter a posição global do clique
                pos = event.globalPosition().toPoint()

                # Geometria do container
                rect_zk = self.container_pesquisa_zk.geometry()
                rect_zk.moveTo(self.container_pesquisa_zk.mapToGlobal(QPoint(0,0)))

                # Geometria dos componentes de busca (para não fechar ao clicar neles)
                rect_toggle = self.btn_toggle_busca.geometry()
                rect_toggle.moveTo(self.btn_toggle_busca.mapToGlobal(QPoint(0,0)))

                rect_busca = self.input_busca.geometry()
                rect_busca.moveTo(self.input_busca.mapToGlobal(QPoint(0,0)))

                rect_busca_cpf = self.input_busca_cpf.geometry()
                rect_busca_cpf.moveTo(self.input_busca_cpf.mapToGlobal(QPoint(0,0)))

                if not rect_zk.contains(pos) and not rect_toggle.contains(pos) and \
                   not rect_busca.contains(pos) and not rect_busca_cpf.contains(pos):
                    self.container_pesquisa_zk.hide()

        return super().eventFilter(obj, event)

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
