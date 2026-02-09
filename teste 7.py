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
        QLineEdit, QPushButton, QLabel, QSplitter, QTextEdit, QTextBrowser, QGroupBox
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
except ImportError as e:
    print("\n" + "="*60)
    print("ERRO CRÍTICO: BIBLIOTECAS NÃO ENCONTRADAS")
    print("="*60)
    print(f"Erro detalhado: {e}")
    print("\nPara corrigir, abra o terminal e digite:")
    print("pip install PyQt6 PyQt6-WebEngine")
    print("="*60 + "\n")
    # Em ambientes sem input (alguns IDEs), isso evita travamento, 
    # mas mantemos o sys.exit para parar a execução.
    sys.exit(1)

# --- CLASSE CUSTOMIZADA PARA NAVEGAÇÃO EM JANELA ÚNICA ---
class CustomWebPage(QWebEnginePage):
    """
    Página customizada que força todos os links (target='_blank', window.open, etc)
    a abrirem na mesma janela do navegador.
    """
    def createWindow(self, _type):
        # Quando o site pede para criar uma nova janela (ex: Link do WhatsApp),
        # retornamos 'self'. Isso diz ao Qt: "Use esta mesma janela/aba para carregar o link".
        print(">>> Interceptando tentativa de abrir nova janela -> Forçando na mesma página.")
        return self

class DatabaseHandler:
    def __init__(self, db_name="dados_detalhes.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.criar_tabelas()

    def criar_tabelas(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS detalhes_visitas (
                visita_id INTEGER PRIMARY KEY,
                conteudo TEXT,
                url TEXT,
                data_captura TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def salvar_visita(self, visita_id, conteudo, url):
        try:
            self.cursor.execute('INSERT OR REPLACE INTO detalhes_visitas (visita_id, conteudo, url) VALUES (?, ?, ?)', 
                               (visita_id, conteudo, url))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[ERRO SQL] {e}")
            return False

    def buscar_todos(self):
        self.cursor.execute("SELECT visita_id, conteudo, url FROM detalhes_visitas ORDER BY visita_id DESC")
        return self.cursor.fetchall()

    def get_maior_id_salvo(self):
        self.cursor.execute("SELECT MAX(visita_id) FROM detalhes_visitas")
        res = self.cursor.fetchone()
        return res[0] if res[0] else 0

class SmartPortariaScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monitor Portaria - Automático (Janela Única)")
        self.resize(1400, 900)
        
        self.db = DatabaseHandler()
        self.id_atual = 1
        self.rodando = True
        
        self.timer_retry = QTimer()
        self.timer_retry.setSingleShot(True)
        self.timer_retry.timeout.connect(self.carregar_url_id)

        self.setup_ui()
        self.carregar_ultimo_id()
        self.configurar_navegadores()
        
        # URL Inicial
        self.view_principal.setUrl(QUrl("https://portaria-global.governarti.com.br/"))

        self.txt_live.append(f"--- SISTEMA INICIADO: {datetime.datetime.now().strftime('%H:%M:%S')} ---")
        self.txt_live.append(">>> Monitoramento automático ativado.")
        QTimer.singleShot(2000, self.carregar_url_id)

    def setup_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QHBoxLayout(self.central)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PAINEL ESQUERDO (Status e Busca) ---
        painel = QWidget()
        painel.setFixedWidth(450)
        lat = QVBoxLayout(painel)

        self.status_box = QWidget()
        self.status_box.setStyleSheet("background: #f1f5f9; border-radius: 8px; padding: 10px; border: 1px solid #ccc;")
        status_lat = QVBoxLayout(self.status_box)
        self.lbl_id_viva = QLabel("ID ATUAL: --")
        self.lbl_id_viva.setStyleSheet("font-size: 22px; font-weight: bold; color: #2563eb;")
        self.lbl_status = QLabel("Monitorando em 2º plano...")
        self.lbl_status.setWordWrap(True)
        status_lat.addWidget(self.lbl_id_viva)
        status_lat.addWidget(self.lbl_status)
        lat.addWidget(self.status_box)

        group_live = QGroupBox("CAPTURAS EM TEMPO REAL")
        layout_live = QVBoxLayout(group_live)
        self.txt_live = QTextEdit()
        self.txt_live.setReadOnly(True)
        self.txt_live.setStyleSheet("background: #1e293b; color: #4ade80; font-family: Consolas, monospace; font-size: 12px;")
        layout_live.addWidget(self.txt_live)
        lat.addWidget(group_live)

        group_busca = QGroupBox("BUSCA NO BANCO DE DADOS")
        layout_busca = QVBoxLayout(group_busca)
        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Filtrar capturas antigas...")
        self.input_busca.textChanged.connect(self.realizar_busca_local)
        layout_busca.addWidget(self.input_busca)
        
        self.txt_res_busca = QTextBrowser()
        self.txt_res_busca.setOpenExternalLinks(False)
        self.txt_res_busca.setMaximumHeight(200)
        self.txt_res_busca.anchorClicked.connect(self.abrir_link_resultado)
        layout_busca.addWidget(self.txt_res_busca)
        lat.addWidget(group_busca)

        # --- NAVEGADOR PRINCIPAL (Janela Única) ---
        container_web = QWidget()
        layout_web = QVBoxLayout(container_web)
        layout_web.setContentsMargins(0, 0, 0, 0)

        # Barra de Ferramentas
        toolbar = QHBoxLayout()
        self.btn_back = QPushButton("←")
        self.btn_back.setFixedWidth(30)
        self.btn_forward = QPushButton("→")
        self.btn_forward.setFixedWidth(30)
        self.btn_reload = QPushButton("↻")
        self.btn_reload.setFixedWidth(30)
        
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Introduza o URL ou pesquise...")
        self.address_bar.returnPressed.connect(self.ir_para_url)

        # Botão para ir para a Home
        self.btn_home = QPushButton("🏠 Portaria Global")
        self.btn_home.setStyleSheet("padding: 5px; font-weight: bold;")
        self.btn_home.clicked.connect(self.ir_para_home)

        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_reload)
        toolbar.addWidget(self.address_bar)
        toolbar.addWidget(self.btn_home)
        
        layout_web.addLayout(toolbar)

        self.view_principal = QWebEngineView()
        
        # --- APLICAÇÃO DA LÓGICA DE JANELA ÚNICA ---
        # Usamos o perfil padrão para manter logins e cookies.
        profile = QWebEngineProfile.defaultProfile()
        custom_page = CustomWebPage(profile, self.view_principal)
        self.view_principal.setPage(custom_page)
        # -------------------------------------------
        
        self.view_principal.urlChanged.connect(self.atualizar_barra_endereco)
        self.btn_back.clicked.connect(self.view_principal.back)
        self.btn_forward.clicked.connect(self.view_principal.forward)
        self.btn_reload.clicked.connect(self.view_principal.reload)
        self.view_principal.loadFinished.connect(self.on_principal_load_finished)
        
        layout_web.addWidget(self.view_principal)

        # Navegador Worker (Invisível - usado para varredura)
        self.view_worker = QWebEngineView()
        self.view_worker.setVisible(False)
        self.view_worker.loadFinished.connect(self.on_worker_load_finished)
        
        splitter.addWidget(painel)
        splitter.addWidget(container_web)
        layout.addWidget(splitter)

    def ir_para_url(self):
        url_texto = self.address_bar.text()
        if not url_texto.startswith("http"):
            url_texto = "https://" + url_texto
        self.view_principal.setUrl(QUrl(url_texto))

    def ir_para_home(self):
        self.view_principal.setUrl(QUrl("https://portaria-global.governarti.com.br/"))

    def atualizar_barra_endereco(self, qurl):
        self.address_bar.setText(qurl.toString())

    def log(self, tag, msg):
        hora = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"[{hora}] [{tag}] {msg}")
        self.lbl_status.setText(f"[{hora}] {msg}")

    def configurar_navegadores(self):
        # Configurações do Worker (Otimizado para velocidade)
        s_worker = self.view_worker.settings()
        s_worker.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, False)
        s_worker.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        # Configurações do Principal (Otimizado para usabilidade)
        # Nota: As configurações devem ser aplicadas na página customizada que já setamos
        s_main = self.view_principal.page().settings()
        s_main.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        s_main.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        # Permite JS abrir janelas (que nosso CustomWebPage vai interceptar e forçar na mesma)
        s_main.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        s_main.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        s_main.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

    def carregar_ultimo_id(self):
        maior = self.db.get_maior_id_salvo()
        if maior > 0: self.id_atual = maior + 1
        self.lbl_id_viva.setText(f"ID ATUAL: {self.id_atual}")

    def carregar_url_id(self):
        if not self.rodando: return
        self.lbl_id_viva.setText(f"ID ATUAL: {self.id_atual}")
        url = f"https://portaria-global.governarti.com.br/visita/{self.id_atual}/detalhes?t={datetime.datetime.now().timestamp()}"
        self.view_worker.setUrl(QUrl(url))

    def injetar_login(self, browser_view):
        # Verifica a URL atual antes de injetar
        url_atual = browser_view.url().toString()
        
        # Só preenche se estiver na página de login
        if "portaria-global.governarti.com.br/login" in url_atual:
            # Script para preencher login automaticamente caso caia na tela de login
            js_login = "document.querySelectorAll('input').forEach(i => { if(i.type=='text') i.value='armando.junior'; if(i.type=='password') i.value='armandocampos.1'; });"
            browser_view.page().runJavaScript(js_login)

    def on_principal_load_finished(self, ok):
        self.injetar_login(self.view_principal)

    def on_worker_load_finished(self, ok):
        self.injetar_login(self.view_worker)
        if self.rodando:
            QTimer.singleShot(800, self.extrair_e_validar)

    def extrair_e_validar(self):
        self.view_worker.page().runJavaScript("document.body.innerText;", self.callback_validacao)

    def callback_validacao(self, conteudo):
        if not self.rodando: return

        # Se o conteúdo for None ou parecer página de login, tenta de novo
        if not conteudo or "entrar" in conteudo.lower()[:300]:
            self.log("SESSÃO", "Worker pediu login. Tentando reautenticar...")
            self.timer_retry.start(3000)
            return

        match_nome = re.search(r"Visitante:\s*([\w\.\s\-]+)", conteudo, re.IGNORECASE)
        match_cpf = re.search(r"(\d{3}\.\d{3}\.\d{3}-\d{2})", conteudo)

        dados_encontrados = (match_nome or match_cpf) and "não encontrada" not in conteudo.lower()

        if dados_encontrados:
            self.db.salvar_visita(self.id_atual, conteudo, self.view_worker.url().toString())
            nome_str = match_nome.group(1).strip() if match_nome else "Nome Desconhecido"
            # Limpeza básica do nome
            nome_str = nome_str.split("Telefone")[0].split("CPF")[0].strip(" -")
            cpf_str = match_cpf.group(1) if match_cpf else "Doc N/A"
            
            log_entry = f"ID {self.id_atual}: {nome_str} - {cpf_str}"
            self.txt_live.append(log_entry)
            self.log("ACHOU", f"Capturado: {nome_str}")
            
            self.id_atual += 1
            QTimer.singleShot(500, self.carregar_url_id)
        else:
            self.log("AGUARDANDO", f"ID {self.id_atual} ainda não registrado. Tentando novamente em 10s...")
            self.timer_retry.start(10000)

    def realizar_busca_local(self):
        termo = self.input_busca.text().strip().lower()
        if not termo: 
            self.txt_res_busca.clear()
            return
        
        termos = termo.split()
        dados = self.db.buscar_todos()
        html = ""
        
        reg_nome = r"Visitante:\s*([\w\.\s\-]+)"
        reg_cpf = r"(\d{3}\.\d{3}\.\d{3}-\d{2})"
        
        for vid, txt, url in dados:
            m_nome = re.search(reg_nome, txt, re.IGNORECASE)
            m_cpf = re.search(reg_cpf, txt)
            
            if m_nome or m_cpf:
                raw_nome = m_nome.group(1).strip() if m_nome else "N/A"
                cpf = m_cpf.group(1) if m_cpf else "N/A"

                if cpf in raw_nome:
                    raw_nome = raw_nome.replace(cpf, "")

                clean_nome = raw_nome.split("Telefone")[0].split("CPF")[0].split("Celular")[0].strip(" -")
                texto_completo = f"{clean_nome} {cpf}"
                
                # Filtra se todos os termos digitados estão no texto
                if all(t in texto_completo.lower() for t in termos):
                    html += f"""
                    <div style='margin-bottom:8px; padding-bottom:5px; border-bottom:1px solid #ddd;'>
                        <b>ID {vid}:</b> {clean_nome} - {cpf}<br>
                        <a href="{vid}" style="text-decoration:none; color:white; background-color:#16a34a; padding:2px 8px; border-radius:3px; font-size:10px;">ABRIR NO SISTEMA</a>
                    </div>
                    """
        self.txt_res_busca.setHtml(html)

    def abrir_link_resultado(self, url_qurl):
        # Ação ao clicar no botão "ABRIR NO SISTEMA" da busca
        visita_id = url_qurl.toString()
        link_final = f"https://portaria-global.governarti.com.br/visita/{visita_id}/detalhes"
        self.view_principal.setUrl(QUrl(link_final))

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        win = SmartPortariaScanner()
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        print("\n" + "="*60)
        print("OCORREU UM ERRO DURANTE A EXECUÇÃO")
        print("="*60)
        traceback.print_exc()
        print("="*60 + "\n")
        input("Pressione ENTER para fechar...")
