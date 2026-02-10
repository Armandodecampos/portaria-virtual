import sys
import sqlite3
import re
import datetime
import traceback

# --- BLOCO DE PROTEÇÃO DE IMPORTAÇÃO ---
try:
    from PyQt6.QtCore import Qt, QUrl, QTimer
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLineEdit, QPushButton, QLabel, QSplitter, QTextEdit, QTextBrowser, QGroupBox,
        QStackedWidget, QTabBar, QMessageBox, QDialog
    )
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
    import qrcode
    from PIL.ImageQt import ImageQt
except ImportError as e:
    print("\n" + "="*60)
    print("ERRO CRÍTICO: BIBLIOTECAS NÃO ENCONTRADAS")
    print("="*60)
    print(f"Erro detalhado: {e}")
    print("\nPara corrigir, abra o terminal e digite:")
    print("pip install PyQt6 PyQt6-WebEngine")
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
        current_profile = self.profile()
        new_view = self.browser_window.add_new_tab(QUrl(""), "Nova Guia", profile=current_profile)
        return new_view.page()

class QRDialog(QDialog):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Code Gerado")
        self.setModal(True)
        self.setStyleSheet("background-color: white;")

        # Faz a janela ocupar toda a tela/página
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        layout = QVBoxLayout(self)
        layout.addStretch() # Espaço flexível no topo

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
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch() # Espaço flexível na base

        self.showFullScreen()

class DatabaseHandler:
    def __init__(self, db_name="dados_detalhes.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
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

    def buscar_por_filtro(self, termos):
        if not termos: return []
        query = "SELECT visita_id, nome, cpf, horario FROM detalhes_visitas WHERE "
        conditions = []
        params = []
        for t in termos:
            conditions.append("(nome LIKE ? OR cpf LIKE ?)")
            params.extend([f"%{t}%", f"%{t}%"])
        query += " AND ".join(conditions)
        query += " ORDER BY visita_id DESC LIMIT 50"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def get_maior_id_salvo(self):
        self.cursor.execute("SELECT MAX(visita_id) FROM detalhes_visitas")
        res = self.cursor.fetchone()
        return res[0] if res[0] else 0

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
        self.setWindowTitle("Monitor Portaria")
        self.resize(1400, 900)
        
        self.db = DatabaseHandler()
        self.id_atual = 1
        self.rodando = True
        
        self.timer_retry = QTimer()
        self.timer_retry.setSingleShot(True)
        self.timer_retry.timeout.connect(self.carregar_url_id)

        self.profile_anonimo = QWebEngineProfile(self) 
        self.profile_anonimo.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.setup_ui()
        self.carregar_ultimo_id()
        self.configurar_navegadores()

        self.timer_busca = QTimer()
        self.timer_busca.setSingleShot(True)
        self.timer_busca.timeout.connect(self.executar_busca_local)
        
        self.add_new_tab(QUrl("https://portaria-global.governarti.com.br/visitas/"), "Portaria Virtual", closable=False)
        self.add_new_tab(QUrl("about:blank"), "Guia anônima", closable=False, profile=self.profile_anonimo)
        
        self.tabs.setCurrentIndex(0)
        self.web_stack.setCurrentIndex(0)

        self.txt_live.append(f"--- SISTEMA INICIADO: {datetime.datetime.now().strftime('%H:%M:%S')} ---")
        QTimer.singleShot(2000, self.carregar_url_id)

    def setup_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QHBoxLayout(self.central)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PAINEL ESQUERDO ---
        painel = QWidget()
        painel.setFixedWidth(450)
        lat = QVBoxLayout(painel)

        group_busca = QGroupBox("BUSCA NO BANCO DE DADOS")
        layout_busca = QVBoxLayout(group_busca)
        
        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Buscar")
        self.input_busca.setStyleSheet("""
            QLineEdit { padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; font-size: 13px; }
            QLineEdit:focus { border: 2px solid #2563eb; }
        """)
        self.input_busca.textChanged.connect(self.realizar_busca_local)
        layout_busca.addWidget(self.input_busca)
        
        self.txt_res_busca = QTextBrowser()
        self.txt_res_busca.setOpenExternalLinks(False)
        self.txt_res_busca.setMaximumHeight(400)
        self.txt_res_busca.setStyleSheet("border: none; background: transparent;")
        self.txt_res_busca.anchorClicked.connect(self.abrir_link_resultado)
        layout_busca.addWidget(self.txt_res_busca)
        lat.addWidget(group_busca)

        group_live = QGroupBox("LOG DO SISTEMA")
        layout_live = QVBoxLayout(group_live)
        self.txt_live = QTextEdit()
        self.txt_live.setReadOnly(True)
        self.txt_live.setStyleSheet("background: #1e293b; color: #4ade80; font-family: Consolas, monospace; font-size: 12px;")
        layout_live.addWidget(self.txt_live)
        lat.addWidget(group_live)

        group_qr = QGroupBox("Gerador de QR code")
        layout_qr = QVBoxLayout(group_qr)
        self.txt_qr_input = QTextEdit()
        self.txt_qr_input.setPlaceholderText("Cole a mensagem aqui para extrair o link...")
        self.txt_qr_input.setMaximumHeight(100)
        self.txt_qr_input.setStyleSheet("border: 1px solid #cbd5e1; border-radius: 6px;")
        layout_qr.addWidget(self.txt_qr_input)

        btns_layout = QHBoxLayout()
        self.btn_open_anon = QPushButton("Abrir na Guia Anônima")
        self.btn_open_anon.setStyleSheet("background-color: #334155; color: white; padding: 8px; border-radius: 4px;")
        self.btn_open_anon.clicked.connect(self.abrir_qr_na_anonima)

        self.btn_gen_qr = QPushButton("Gerar QR Code")
        self.btn_gen_qr.setStyleSheet("background-color: #2563eb; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.btn_gen_qr.clicked.connect(self.mostrar_qr_code)

        btns_layout.addWidget(self.btn_open_anon)
        btns_layout.addWidget(self.btn_gen_qr)
        layout_qr.addLayout(btns_layout)
        lat.addWidget(group_qr)

        # --- NAVEGADOR PRINCIPAL ---
        container_web = QWidget()
        layout_web = QVBoxLayout(container_web)
        layout_web.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.btn_back = QPushButton("←")
        self.btn_back.setFixedWidth(30)
        self.btn_forward = QPushButton("→")
        self.btn_forward.setFixedWidth(30)
        self.btn_reload = QPushButton("↻")
        self.btn_reload.setFixedWidth(30)
        
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Introduza o URL...")
        self.address_bar.returnPressed.connect(self.ir_para_url)

        self.btn_unlock = QPushButton("Destravar")
        self.btn_unlock.setStyleSheet("background-color: #f59e0b; color: white; font-weight: bold; border-radius: 4px; padding: 5px 10px;")
        self.btn_unlock.clicked.connect(self.executar_desbloqueio)

        # Configuração refinada do QTabBar
        self.tabs = QTabBar()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet("""
            QTabBar::tab { 
                background: #f1f5f9; 
                padding: 8px 55px 8px 12px; /* Espaço generoso à direita */
                border: 1px solid #cbd5e1; 
                margin-right: 4px; 
                border-radius: 6px; 
                min-width: 130px; 
                max-width: 200px; 
                color: #334155;
            } 
            QTabBar::tab:selected { 
                background: #2563eb; 
                color: white; 
                font-weight: bold; 
                border: 1px solid #1d4ed8;
            }
            /* O segredo para afastar da borda direita: subcontrol-position e right */
            QTabBar::close-button {
                subcontrol-origin: border;
                subcontrol-position: right center;
                right: 25px;
                width: 16px;
                height: 16px;
            }
            QTabBar::close-button:hover {
                background-color: rgba(0,0,0,0.1);
                border-radius: 2px;
            }
        """)
        self.tabs.tabCloseRequested.connect(self.fechar_aba)
        self.tabs.currentChanged.connect(self.mudar_aba)

        self.btn_home = QPushButton("🏠")
        self.btn_home.setFixedWidth(35)
        self.btn_home.clicked.connect(self.ir_para_home)

        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_reload)
        toolbar.addWidget(self.btn_unlock)
        toolbar.addWidget(self.address_bar)
        toolbar.addWidget(self.tabs)
        toolbar.addWidget(self.btn_home)
        layout_web.addLayout(toolbar)

        self.web_stack = QStackedWidget()
        layout_web.addWidget(self.web_stack)

        self.btn_back.clicked.connect(lambda: self.web_stack.currentWidget().back() if self.web_stack.currentWidget() else None)
        self.btn_forward.clicked.connect(lambda: self.web_stack.currentWidget().forward() if self.web_stack.currentWidget() else None)
        self.btn_reload.clicked.connect(lambda: self.web_stack.currentWidget().reload() if self.web_stack.currentWidget() else None)

        self.view_worker = QWebEngineView()
        self.view_worker.setVisible(False)
        self.view_worker.loadFinished.connect(self.on_worker_load_finished)
        
        splitter.addWidget(painel)
        splitter.addWidget(container_web)
        layout.addWidget(splitter)

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
        else:
            btn = self.tabs.tabButton(tab_idx, QTabBar.ButtonPosition.RightSide)
            if btn: btn.setToolTip("Fechar aba")
            
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
            if view.page().profile() == self.profile_anonimo: view.setUrl(QUrl("https://www.google.com"))
            else: view.setUrl(QUrl("https://portaria-global.governarti.com.br/visitas/"))

    def mudar_aba(self, index):
        if index >= 0:
            self.web_stack.setCurrentIndex(index)
            view = self.web_stack.currentWidget()
            if view:
                url_str = view.url().toString()
                self.address_bar.setText("" if url_str == "about:blank" else url_str)

    def fechar_aba(self, index):
        titulo = self.tabs.tabText(index)
        if "Portaria Virtual" in titulo or "anônima" in titulo.lower(): return
        widget = self.web_stack.widget(index)
        if widget:
            self.web_stack.removeWidget(widget)
            widget.deleteLater()
        self.tabs.removeTab(index)

    def atualizar_titulo_aba(self, titulo, view):
        index = self.web_stack.indexOf(view)
        if index != -1:
            current_text = self.tabs.tabText(index)
            if "Portaria Virtual" in current_text or "anônima" in current_text.lower(): return
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
        maior = self.db.get_maior_id_salvo()
        if maior > 0: self.id_atual = maior + 1

    def carregar_url_id(self):
        if not self.rodando: return
        url = f"https://portaria-global.governarti.com.br/visita/{self.id_atual}/detalhes?t={datetime.datetime.now().timestamp()}"
        self.view_worker.setUrl(QUrl(url))

    def injetar_login(self, browser_view):
        if browser_view.page().profile() == self.profile_anonimo: return
        url_atual = browser_view.url().toString()
        if "portaria-global.governarti.com.br/login" in url_atual:
            js_login = "document.querySelectorAll('input').forEach(i => { if(i.type=='text') i.value='armando.junior'; if(i.type=='password') i.value='armandocampos.1'; });"
            browser_view.page().runJavaScript(js_login)

    def on_tab_load_finished(self, ok, view):
        self.injetar_login(view)

    def on_worker_load_finished(self, ok):
        self.injetar_login(self.view_worker)
        if self.rodando: QTimer.singleShot(800, self.extrair_e_validar)

    def extrair_e_validar(self):
        self.view_worker.page().runJavaScript("document.body.innerText;", self.callback_validacao)

    def callback_validacao(self, conteudo):
        if not self.rodando: return
        if not conteudo or "entrar" in conteudo.lower()[:300]:
            self.timer_retry.start(3000)
            return

        nome_str, cpf_str, horario_str = self.db.extrair_dados(conteudo)
        dados_encontrados = (nome_str != "Desconhecido" or cpf_str != "N/A") and "não encontrada" not in conteudo.lower()

        if dados_encontrados:
            self.db.salvar_visita(self.id_atual, nome_str, cpf_str, horario_str, conteudo, self.view_worker.url().toString())
            self.txt_live.append(f"ID {self.id_atual} registrado: {nome_str}")
            self.id_atual += 1
            QTimer.singleShot(500, self.carregar_url_id)
        else:
            self.timer_retry.start(10000)

    def realizar_busca_local(self):
        self.timer_busca.start(300)

    def executar_busca_local(self):
        termo = self.input_busca.text().strip().lower()
        if not termo: 
            self.txt_res_busca.clear()
            return
        termos = termo.split()
        dados = self.db.buscar_por_filtro(termos)
        html = ""
        hoje = datetime.date.today()
        for vid, nome, cpf, horario in dados:
            cor = "green"
            if horario and horario != "N/A":
                try:
                    partes = horario.split(" - ")
                    if len(partes) == 2:
                        data_fim = datetime.datetime.strptime(partes[1].strip(), "%d/%m/%Y").date()
                        if data_fim < hoje: cor = "red"
                except: pass
            html += f"""
            <a href="{vid}" style="text-decoration: none;">
                <div style='background-color: #ffffff; border: 1px solid #cbd5e1; border-bottom: 3px solid #94a3b8; border-radius: 8px; padding: 12px; margin-bottom: 8px;'>
                    <div style='color: #1e293b; font-size: 14px;'>
                        <b style='color: #2563eb;'>ID {vid}:</b> {nome}<br>
                        <span style='color: #64748b; font-size: 12px;'>CPF / ID: {cpf}</span><br>
                        <span style='color: #475569; font-size: 12px;'><b>Validade:</b> <span style='color: {cor}; font-weight: bold;'>{horario}</span></span>
                    </div>
                </div>
            </a>
            """
        self.txt_res_busca.setHtml(html)

    def abrir_link_resultado(self, url_qurl):
        visita_id = url_qurl.toString()
        link_final = f"https://portaria-global.governarti.com.br/visita/{visita_id}/detalhes"
        self.add_new_tab(QUrl(link_final), f"ID {visita_id}")

    def extrair_url_qr(self):
        texto = self.txt_qr_input.toPlainText()
        match = re.search(r'https?://[^\s]+', texto)
        if match:
            return match.group(0).rstrip('.')
        return None

    def abrir_qr_na_anonima(self):
        url = self.extrair_url_qr()
        if not url:
            QMessageBox.warning(self, "Aviso", "Nenhuma URL encontrada na mensagem.")
            return

        # Procura a guia anônima
        for i in range(self.tabs.count()):
            if "anônima" in self.tabs.tabText(i).lower():
                self.tabs.setCurrentIndex(i)
                view = self.web_stack.widget(i)
                if view:
                    view.setUrl(QUrl(url))
                return

        # Se não encontrou (não deveria acontecer), cria uma nova
        self.add_new_tab(QUrl(url), "Guia anônima", closable=False, profile=self.profile_anonimo)

    def mostrar_qr_code(self):
        url = self.extrair_url_qr()
        if not url:
            QMessageBox.warning(self, "Aviso", "Nenhuma URL encontrada na mensagem para gerar QR Code.")
            return

        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(url)
            qr.make(fit=True)
            img_pil = qr.make_image(fill_color="black", back_color="white")

            # Converter PIL image para QPixmap
            # img_pil é um objeto qrcode.image.pil.PilImage, o PIL.Image real está em img_pil._img
            actual_image = img_pil._img
            qimg = ImageQt(actual_image)
            pixmap = QPixmap.fromImage(qimg)

            dlg = QRDialog(pixmap, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao gerar QR Code: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SmartPortariaScanner()
    win.show()
    sys.exit(app.exec())
