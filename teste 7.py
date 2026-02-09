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
        QStackedWidget, QTabBar, QMessageBox
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
        # Verifica se o perfil atual é o anônimo para não logar
        is_anon = (self.profile() == self.browser_window.profile_anonimo)
        
        if not is_anon:
            print(">>> Abrindo link em nova aba.")
            
        # Usa o mesmo perfil da página atual para manter a sessão (ou anonimato)
        current_profile = self.profile()
        new_view = self.browser_window.add_new_tab(QUrl(""), "Nova Guia", profile=current_profile)
        return new_view.page()

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
            print(f">>> Reprocessando {len(registros)} registros para novo formato...")
            for vid, conteudo in registros:
                nome, cpf, horario = self.extrair_dados(conteudo)
                self.cursor.execute("UPDATE detalhes_visitas SET nome = ?, cpf = ?, horario = ? WHERE visita_id = ?", (nome, cpf, horario, vid))
            self.conn.commit()
            print(">>> Reprocessamento concluído.")

    def migrar_dados_vazios(self):
        self.cursor.execute("SELECT visita_id, conteudo FROM detalhes_visitas WHERE nome IS NULL OR cpf IS NULL OR horario IS NULL")
        vazios = self.cursor.fetchall()
        if vazios:
            print(f">>> Migrando {len(vazios)} registros antigos...")
            for vid, conteudo in vazios:
                nome, cpf, horario = self.extrair_dados(conteudo)
                self.cursor.execute("UPDATE detalhes_visitas SET nome = ?, cpf = ?, horario = ? WHERE visita_id = ?", (nome, cpf, horario, vid))
            self.conn.commit()
            print(">>> Migração concluída.")

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
        except Exception as e:
            print(f"[ERRO SQL] {e}")
            return False

    def buscar_todos(self):
        self.cursor.execute("SELECT visita_id, conteudo, url FROM detalhes_visitas ORDER BY visita_id DESC")
        return self.cursor.fetchall()

    def buscar_por_filtro(self, termos):
        if not termos:
            return []

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
        horario = "N/A"

        if m_horario:
            horario = f"{m_horario.group(1)} - {m_horario.group(2)}"

        if cpf != "N/A" and cpf in raw_nome:
            raw_nome = raw_nome.replace(cpf, "")

        clean_nome = raw_nome.split("Telefone")[0].split("CPF")[0].split("Celular")[0].split("Horário")[0].strip(" -")

        if cpf == "N/A" and " - " in clean_nome:
            partes = [p.strip() for p in clean_nome.split(" - ") if p.strip()]
            if len(partes) >= 2:
                possivel_id = partes[-1]
                if any(char.isdigit() for char in possivel_id):
                    cpf = possivel_id
                    clean_nome = " - ".join(partes[:-1]).strip(" -")

        if not clean_nome:
            clean_nome = "Desconhecido"

        return clean_nome, cpf, horario

class SmartPortariaScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monitor Portaria + Unlocker (Versão Especial)")
        self.resize(1400, 900)
        
        self.db = DatabaseHandler()
        self.id_atual = 1
        self.rodando = True
        
        self.timer_retry = QTimer()
        self.timer_retry.setSingleShot(True)
        self.timer_retry.timeout.connect(self.carregar_url_id)

        # Configuração de Perfil Anônimo
        # Criamos um perfil novo sem nome de armazenamento, tornando-o "Off-the-record"
        self.profile_anonimo = QWebEngineProfile(self) 
        # (Opcional) Define User Agent específico para a guia anônima se necessário
        self.profile_anonimo.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.setup_ui()
        self.carregar_ultimo_id()
        self.configurar_navegadores()

        self.timer_busca = QTimer()
        self.timer_busca.setSingleShot(True)
        self.timer_busca.timeout.connect(self.executar_busca_local)
        
        # Aba Inicial (Portaria Virtual - Perfil Padrão)
        self.add_new_tab(QUrl("https://portaria-global.governarti.com.br/"), "Portaria Virtual", closable=False)

        # --- NOVA GUIA ANÔNIMA FIXA ---
        # Abre uma aba em branco ou URL especifica com o perfil anônimo
        self.add_new_tab(QUrl("about:blank"), "Guia anônima", closable=False, profile=self.profile_anonimo)

        self.txt_live.append(f"--- SISTEMA INICIADO: {datetime.datetime.now().strftime('%H:%M:%S')} ---")
        # Removido log de ativação da guia anônima para manter discrição
        
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
        layout_busca.setContentsMargins(10, 15, 10, 10)
        
        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Filtrar capturas antigas...")
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

        self.status_box = QWidget()
        self.status_box.setStyleSheet("background: #f1f5f9; border-radius: 8px; padding: 10px; border: 1px solid #ccc;")
        status_lat = QVBoxLayout(self.status_box)
        self.lbl_id_viva = QLabel("ID ATUAL: --")
        self.lbl_id_viva.setStyleSheet("font-size: 22px; font-weight: bold; color: #2563eb;")
        self.lbl_status = QLabel("Monitorando...")
        self.lbl_status.setWordWrap(True)
        status_lat.addWidget(self.lbl_id_viva)
        status_lat.addWidget(self.lbl_status)
        lat.addWidget(self.status_box)

        group_live = QGroupBox("LOG DO SISTEMA")
        layout_live = QVBoxLayout(group_live)
        self.txt_live = QTextEdit()
        self.txt_live.setReadOnly(True)
        self.txt_live.setStyleSheet("background: #1e293b; color: #4ade80; font-family: Consolas, monospace; font-size: 12px;")
        layout_live.addWidget(self.txt_live)
        lat.addWidget(group_live)

        # --- NAVEGADOR PRINCIPAL ---
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
        self.address_bar.setPlaceholderText("Introduza o URL...")
        self.address_bar.returnPressed.connect(self.ir_para_url)

        # BOTÃO MÁGICO DE DESBLOQUEIO
        self.btn_unlock = QPushButton("Destravar")
        self.btn_unlock.setToolTip("Forçar desbloqueio de botões e pular vídeos")
        self.btn_unlock.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b; color: white; font-weight: bold; 
                border-radius: 4px; padding: 5px 10px;
            }
            QPushButton:hover { background-color: #d97706; }
        """)
        self.btn_unlock.clicked.connect(self.executar_desbloqueio)

        self.tabs = QTabBar()
        self.tabs.setTabsClosable(True)
        self.tabs.setExpanding(False)
        self.tabs.setMovable(False)
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                background: #f1f5f9; padding: 6px 12px; border: 1px solid #cbd5e1;
                margin-right: 2px; border-radius: 4px; min-width: 100px; max-width: 180px;
            }
            QTabBar::tab:selected { background: #2563eb; color: white; font-weight: bold; }
            QTabBar::close-button { margin-right: 15px; }
        """)
        self.tabs.tabCloseRequested.connect(self.fechar_aba)
        self.tabs.currentChanged.connect(self.mudar_aba)

        self.btn_home = QPushButton("🏠")
        self.btn_home.setFixedWidth(35)
        self.btn_home.clicked.connect(self.ir_para_home)

        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_reload)
        toolbar.addWidget(self.btn_unlock) # Adicionado botão unlock
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

    # Modificado para aceitar perfil personalizado
    def add_new_tab(self, qurl, title, closable=True, profile=None):
        view = QWebEngineView()
        
        # Se nenhum perfil for passado, usa o padrão. Se passado (ex: anônimo), usa ele.
        target_profile = profile if profile else QWebEngineProfile.defaultProfile()
        
        page = CustomWebPage(target_profile, view, self)
        view.setPage(page)

        s = view.page().settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        # Permite reprodução de vídeo automática
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

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
        """
        Injeta JavaScript para forçar a habilitação de botões e pular vídeos.
        """
        view = self.web_stack.currentWidget()
        if not view: return

        # JavaScript avançado para desbloqueio
        js_hack = """
        (function() {
            var log = [];
            
            // 1. Remover atributos disabled e classes de bloqueio
            var disabledEls = document.querySelectorAll('*[disabled], .disabled, .blocked, .locked, [aria-disabled="true"]');
            disabledEls.forEach(el => {
                el.removeAttribute('disabled');
                el.classList.remove('disabled', 'blocked', 'locked');
                el.setAttribute('aria-disabled', 'false');
                el.style.pointerEvents = 'auto';
                el.style.opacity = '1';
                el.style.filter = 'none';
                el.style.cursor = 'pointer';
            });
            log.push(disabledEls.length + " elementos desbloqueados.");

            // 2. Manipular Vídeos (Fazer o vídeo "pensar" que acabou)
            var videos = document.querySelectorAll('video');
            videos.forEach(v => {
                if(!v.paused && v.duration) {
                    // Pula para o final
                    v.currentTime = v.duration; 
                    // Dispara eventos de conclusão
                    v.dispatchEvent(new Event('ended'));
                    v.dispatchEvent(new Event('timeupdate'));
                } else if (v.duration) {
                    // Mesmo se pausado, força o fim
                    v.currentTime = v.duration;
                    v.dispatchEvent(new Event('ended'));
                }
            });
            log.push(videos.length + " vídeos pulados.");

            return log.join(' | ');
        })();
        """
        
        # Executa o JS. Só loga se NÃO for anônimo.
        def callback_js(res):
            if view.page().profile() != self.profile_anonimo:
                self.txt_live.append(f"🔓 DESBLOQUEIO: {res}")

        view.page().runJavaScript(js_hack, callback_js)
        
        if view.page().profile() != self.profile_anonimo:
            self.txt_live.append(">>> Tentativa de desbloqueio enviada!")

    def ir_para_url(self):
        url_texto = self.address_bar.text().strip()
        
        # Se estiver vazio, não faz nada. 
        if not url_texto:
            return

        # Lógica de navegação: se o usuário digitou "about:blank" explicitamente, deixa passar.
        # Caso contrário, adiciona o protocolo se faltar.
        if url_texto == "about:blank":
             pass 
        elif not url_texto.startswith("http") and not url_texto.startswith("about:"):
            url_texto = "https://" + url_texto
        
        view = self.web_stack.currentWidget()
        if view:
            print(f">>> Navegando para: {url_texto}")
            view.setUrl(QUrl(url_texto))

    def ir_para_home(self):
        view = self.web_stack.currentWidget()
        if view:
            # Se for anônimo, talvez ir para o google ou blank seja melhor que a portaria
            if view.page().profile() == self.profile_anonimo:
                view.setUrl(QUrl("https://www.google.com"))
            else:
                view.setUrl(QUrl("https://portaria-global.governarti.com.br/"))

    def mudar_aba(self, index):
        if index >= 0:
            self.web_stack.setCurrentIndex(index)
            view = self.web_stack.currentWidget()
            if view:
                url_str = view.url().toString()
                if url_str == "about:blank":
                    self.address_bar.clear()
                    self.address_bar.setPlaceholderText("Guia anônima - Digite URL...")
                else:
                    self.address_bar.setText(url_str)

    def fechar_aba(self, index):
        # Protege Portaria Virtual e Guia Anônima
        titulo = self.tabs.tabText(index)
        if "Portaria Virtual" in titulo or "anônima" in titulo.lower():
            # Só loga tentativa de fecho se NÃO for a guia anônima envolvida (para garantir sigilo total)
            # Mas aqui o log é sobre a ação do usuário na interface, então pode ser útil saber.
            # Vou silenciar se for a anônima.
            if "anônima" not in titulo.lower():
                self.txt_live.append(">>> Tentativa de fechar guia protegida bloqueada.")
            return

        widget = self.web_stack.widget(index)
        if widget:
            self.web_stack.removeWidget(widget)
            widget.deleteLater()
        self.tabs.removeTab(index)

    def atualizar_titulo_aba(self, titulo, view):
        index = self.web_stack.indexOf(view)
        if index != -1:
            # Mantém nomes fixos para as guias especiais
            current_text = self.tabs.tabText(index)
            if "Portaria Virtual" in current_text: return
            if "anônima" in current_text.lower(): return

            display_title = titulo[:15] + "..." if len(titulo) > 15 else titulo
            self.tabs.setTabText(index, display_title)

    def atualizar_barra_endereco(self, qurl, view):
        if view == self.web_stack.currentWidget():
            url_str = qurl.toString()
            # Se a página for about:blank, mantemos a barra limpa (ou com o texto que o usuário está digitando se não for um evento de reset)
            # Na prática, urlChanged é disparado quando a página carrega.
            if url_str == "about:blank":
                self.address_bar.clear()
                self.address_bar.setPlaceholderText("Guia anônima - Digite URL...")
            else:
                self.address_bar.setText(url_str)

    def log(self, tag, msg):
        # Verifica se o log vem de uma ação do usuário na aba anônima?
        # A função log é usada principalmente pelo worker.
        hora = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"[{hora}] [{tag}] {msg}")
        self.lbl_status.setText(f"[{hora}] {msg}")

    def configurar_navegadores(self):
        s_worker = self.view_worker.settings()
        s_worker.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, False)
        s_worker.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

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
        # Se for anônimo, não injeta login automático para não deixar rastros ou vazar credenciais
        if browser_view.page().profile() == self.profile_anonimo:
            return

        url_atual = browser_view.url().toString()
        if "portaria-global.governarti.com.br/login" in url_atual:
            js_login = "document.querySelectorAll('input').forEach(i => { if(i.type=='text') i.value='armando.junior'; if(i.type=='password') i.value='armandocampos.1'; });"
            browser_view.page().runJavaScript(js_login)

    def on_tab_load_finished(self, ok, view):
        self.injetar_login(view)

    def on_worker_load_finished(self, ok):
        self.injetar_login(self.view_worker)
        if self.rodando:
            QTimer.singleShot(800, self.extrair_e_validar)

    def extrair_e_validar(self):
        self.view_worker.page().runJavaScript("document.body.innerText;", self.callback_validacao)

    def callback_validacao(self, conteudo):
        if not self.rodando: return
        if not conteudo or "entrar" in conteudo.lower()[:300]:
            self.log("SESSÃO", "Worker pediu login. Tentando reautenticar...")
            self.timer_retry.start(3000)
            return

        nome_str, cpf_str, horario_str = self.db.extrair_dados(conteudo)
        dados_encontrados = (nome_str != "Desconhecido" or cpf_str != "N/A") and "não encontrada" not in conteudo.lower()

        if dados_encontrados:
            self.db.salvar_visita(self.id_atual, nome_str, cpf_str, horario_str, conteudo, self.view_worker.url().toString())
            log_entry = f"ID {self.id_atual}: {nome_str} - {cpf_str} - {horario_str}"
            self.txt_live.append(log_entry)
            self.log("ACHOU", f"Capturado: {nome_str}")
            self.id_atual += 1
            QTimer.singleShot(500, self.carregar_url_id)
        else:
            self.log("AGUARDANDO", f"ID {self.id_atual} ainda não registrado. Tentando novamente em 10s...")
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
                        data_fim_str = partes[1].strip()
                        data_fim = datetime.datetime.strptime(data_fim_str, "%d/%m/%Y").date()
                        if data_fim < hoje:
                            cor = "red"
                except Exception:
                    pass

            html += f"""
            <a href="{vid}" style="text-decoration: none;">
                <div style='background-color: #ffffff; border: 2px solid #cbd5e1; border-bottom: 4px solid #94a3b8; border-right: 3px solid #94a3b8; border-radius: 8px; padding: 12px;'>
                    <div style='color: #1e293b; font-size: 14px;'>
                        <b style='color: #2563eb;'>ID {vid}:</b> {nome}<br>
                        <span style='color: #64748b; font-size: 12px;'>CPF / ID: {cpf}</span><br>
                        <span style='color: #475569; font-size: 12px;'><b>Validade:</b> <span style='color: {cor}; font-weight: bold;'>{horario}</span></span>
                    </div>
                </div>
            </a>
            <div style='font-size: 12px;'>&nbsp;</div>
            """
        self.txt_res_busca.setHtml(html)

    def abrir_link_resultado(self, url_qurl):
        visita_id = url_qurl.toString()
        link_final = f"https://portaria-global.governarti.com.br/visita/{visita_id}/detalhes"
        self.add_new_tab(QUrl(link_final), f"ID {visita_id}")

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
