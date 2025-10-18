import streamlit as st
import pandas as pd
import sqlite3
import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import hashlib
import re
import numpy as np
import calendar
import requests
import json
import logging

# Importar módulo de integração Octav
from octav_integration import OctavAPI, FundAUMUpdater

# Funções auxiliares para automação
def verificar_configuracao_automacao():
    """Verifica se a atualização automática está ativa e se precisa ser executada"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    try:
        c.execute("SELECT atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas FROM configuracoes_automacao WHERE id = 1")
        config = c.fetchone()
        
        if not config:
            # Criar configuração padrão se não existir
            c.execute("INSERT OR IGNORE INTO configuracoes_automacao (id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) VALUES (1, 1, '', 24)")
            conn.commit()
            return True, True  # Primeira execução
        
        ativa, ultima_atualizacao, intervalo_horas = config
        
        if not ativa:
            return False, False
        
        # Verificar se precisa atualizar
        if not ultima_atualizacao:
            return True, True  # Primeira execução
        
        try:
            ultima_data = datetime.fromisoformat(ultima_atualizacao)
            agora = datetime.now()
            diferenca = agora - ultima_data
            
            if diferenca.total_seconds() >= (intervalo_horas * 3600):
                return True, True
            else:
                return True, False
        except:
            return True, True
    except sqlite3.OperationalError:
        # Tabela não existe, criar e retornar configuração padrão
        c.execute("""CREATE TABLE IF NOT EXISTS configuracoes_automacao (
            id INTEGER PRIMARY KEY,
            atualizacao_automatica_ativa BOOLEAN DEFAULT 1,
            ultima_atualizacao_automatica TEXT,
            intervalo_horas INTEGER DEFAULT 24
        )""")
        c.execute("INSERT INTO configuracoes_automacao (id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) VALUES (1, 1, '', 24)")
        conn.commit()
        return True, True

def executar_atualizacao_automatica():
    """Executa a atualização automática do AUM"""
    try:
        conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
        
        # Executar atualização via Octav API
        api_token, wallet_address = get_octav_config()
        octav_api = OctavAPI(api_token, wallet_address)
        updater = FundAUMUpdater('fundo_usdt.db', octav_api)
        
        portfolio_data = octav_api.get_historical_portfolio()
        if portfolio_data:
            portfolio_value = octav_api.extract_networth(portfolio_data)
            if portfolio_value:
                success = updater.update_aum_from_portfolio(portfolio_value)
                
                if success:
                    # Atualizar timestamp da última atualização automática
                    c = conn.cursor()
                    c.execute("UPDATE configuracoes_automacao SET ultima_atualizacao_automatica = ? WHERE id = 1", 
                             (datetime.now().isoformat(),))
                    conn.commit()
                    return True, f"AUM atualizado automaticamente: ${portfolio_value:,.2f}"
        
        return False, "Erro na atualização automática"
    except Exception as e:
        return False, f"Erro na atualização automática: {str(e)}"

def verificar_aum_atualizado():
    """Verifica se o AUM foi atualizado hoje"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM aum_diario WHERE data = ?", (hoje,))
    count = c.fetchone()[0]
    
    return count > 0

# Configuração da página
st.set_page_config(
    page_title="Fundo USDT - Gestão de Investimentos",
    page_icon="💰",
    layout="wide"
)

# Configurações da API Octav (valores padrão, podem ser alterados via interface)
OCTAV_API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwczovL2hhc3VyYS5pby9qd3QvY2xhaW1zIjp7IngtaGFzdXJhLWRlZmF1bHQtcm9sZSI6InVzZXIiLCJ4LWhhc3VyYS1hbGxvd2VkLXJvbGVzIjpbInVzZXIiXSwieC1oYXN1cmEtdXNlci1pZCI6InNhbnJlbW8yNjE0MSJ9fQ.0eLf5m4kQPETnUaZbN6LFMoV8hxGwjrdZ598r9o61Yc"
OCTAV_WALLET_ADDRESS = "0x3FfDb6ea2084d2BDD62F434cA6B5F610Fa2730aB"

# Funções para gerenciar configurações dinâmicas
def get_octav_config():
    """Obtém configurações atuais da API Octav"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT api_token, wallet_address FROM configuracoes_octav WHERE id = 1")
    config = c.fetchone()
    
    if not config:
        # Inserir configuração padrão se não existir
        c.execute("INSERT INTO configuracoes_octav (id, api_token, wallet_address, ativo) VALUES (1, ?, ?, 1)", 
                 (OCTAV_API_TOKEN, OCTAV_WALLET_ADDRESS))
        conn.commit()
        return OCTAV_API_TOKEN, OCTAV_WALLET_ADDRESS
    
    return config[0] or OCTAV_API_TOKEN, config[1] or OCTAV_WALLET_ADDRESS

def update_octav_config(api_token, wallet_address):
    """Atualiza configurações da API Octav"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute("""INSERT OR REPLACE INTO configuracoes_octav 
                 (id, api_token, wallet_address, ativo, ultima_atualizacao) 
                 VALUES (1, ?, ?, 1, ?)""", 
              (api_token, wallet_address, datetime.now().isoformat()))
    conn.commit()

def get_backup_config():
    """Obtém configurações de backup"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT backup_automatico_ativo, ultimo_backup_automatico, intervalo_backup_horas FROM configuracoes_backup WHERE id = 1")
    config = c.fetchone()
    
    if not config:
        # Inserir configuração padrão se não existir
        c.execute("INSERT INTO configuracoes_backup (id, backup_automatico_ativo, ultimo_backup_automatico, intervalo_backup_horas) VALUES (1, 1, '', 24)")
        conn.commit()
        return True, '', 24
    
    return config

def realizar_backup(tipo='manual'):
    """Realiza backup do banco de dados"""
    import shutil
    import os
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_fundo_{timestamp}.db"
        
        # Fazer cópia do banco
        shutil.copy2('fundo_usdt.db', backup_filename)
        
        # Obter tamanho do arquivo
        tamanho = os.path.getsize(backup_filename)
        
        # Ler conteúdo do arquivo para download
        with open(backup_filename, 'rb') as f:
            backup_content = f.read()
        
        # Registrar no histórico
        conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("""INSERT INTO historico_backups 
                     (timestamp, tipo, arquivo, tamanho, status) 
                     VALUES (?, ?, ?, ?, 'sucesso')""",
                 (datetime.now().isoformat(), tipo, backup_filename, tamanho))
        
        # Atualizar último backup se for automático
        if tipo == 'automatico':
            c.execute("UPDATE configuracoes_backup SET ultimo_backup_automatico = ? WHERE id = 1",
                     (datetime.now().isoformat(),))
        
        conn.commit()
        
        # Limpar arquivo temporário do servidor
        try:
            os.remove(backup_filename)
        except:
            pass
        
        return True, backup_filename, tamanho, backup_content
        
    except Exception as e:
        # Registrar erro
        conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("""INSERT INTO historico_backups 
                     (timestamp, tipo, arquivo, tamanho, status, erro) 
                     VALUES (?, ?, ?, 0, 'erro', ?)""",
                 (datetime.now().isoformat(), tipo, f"backup_erro_{timestamp}.db", str(e)))
        conn.commit()
        
        return False, None, 0, None

def listar_backups_disponiveis():
    """Lista backups disponíveis no histórico"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute("""
        SELECT timestamp, arquivo, tamanho, tipo
        FROM historico_backups 
        WHERE status = 'sucesso'
        ORDER BY timestamp DESC 
        LIMIT 20
    """)
    
    return c.fetchall()

# Conecta ao banco de dados
@st.cache_resource
def init_database():
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    # Cria tabelas se não existirem
    c.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        cotas REAL DEFAULT 0,
        data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS movimentacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        tipo TEXT NOT NULL,
        valor REAL NOT NULL,
        cotas REAL NOT NULL,
        data TEXT DEFAULT CURRENT_TIMESTAMP,
        descricao TEXT,
        FOREIGN KEY (cliente_id) REFERENCES clientes (id)
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS aum_diario (
        data TEXT PRIMARY KEY,
        valor_total REAL NOT NULL,
        valor_cota REAL NOT NULL,
        despesas REAL DEFAULT 0
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        categoria TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS configuracoes_fundo (
        id INTEGER PRIMARY KEY,
        nome_fundo TEXT DEFAULT 'Fundo USDT',
        data_inicio TEXT,
        valor_cota_inicial REAL DEFAULT 1.0,
        aum_inicial REAL DEFAULT 0
    )""")
    
    # Tabela para configurações de automação
    c.execute("""CREATE TABLE IF NOT EXISTS configuracoes_automacao (
        id INTEGER PRIMARY KEY,
        atualizacao_automatica_ativa BOOLEAN DEFAULT 1,
        ultima_atualizacao_automatica TEXT,
        intervalo_horas INTEGER DEFAULT 24
    )""")
    
    # Tabelas adicionais para funcionalidades futuras
    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        tipo TEXT DEFAULT 'cliente',
        ativo BOOLEAN DEFAULT 1,
        data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        endereco TEXT NOT NULL,
        blockchain TEXT NOT NULL,
        ativo BOOLEAN DEFAULT 1
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS exchange_apis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange TEXT NOT NULL,
        api_key TEXT,
        api_secret TEXT,
        ativo BOOLEAN DEFAULT 0
    )""")
    
    # Nova tabela para logs de AUM
    c.execute("""CREATE TABLE IF NOT EXISTS logs_aum (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        tipo TEXT NOT NULL,
        fonte TEXT NOT NULL,
        valor REAL,
        status TEXT NOT NULL,
        detalhes TEXT,
        erro TEXT
    )""")
    
    # Tabela para configurações de backup
    c.execute("""CREATE TABLE IF NOT EXISTS configuracoes_backup (
        id INTEGER PRIMARY KEY,
        backup_automatico_ativo BOOLEAN DEFAULT 1,
        ultimo_backup_automatico TEXT,
        intervalo_backup_horas INTEGER DEFAULT 24,
        local_backup TEXT DEFAULT 'local'
    )""")
    
    # Tabela para histórico de backups
    c.execute("""CREATE TABLE IF NOT EXISTS historico_backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        tipo TEXT NOT NULL,
        arquivo TEXT NOT NULL,
        tamanho INTEGER,
        status TEXT NOT NULL,
        erro TEXT
    )""")
    
    # Tabela para configurações da API Octav
    c.execute("""CREATE TABLE IF NOT EXISTS configuracoes_octav (
        id INTEGER PRIMARY KEY,
        api_token TEXT,
        wallet_address TEXT,
        ativo BOOLEAN DEFAULT 1,
        ultima_atualizacao TEXT
    )""")
    
    # Migração: Adicionar coluna categoria na tabela despesas se não existir
    try:
        c.execute("SELECT categoria FROM despesas LIMIT 1")
    except sqlite3.OperationalError:
        # Coluna não existe, vamos adicioná-la
        c.execute("ALTER TABLE despesas ADD COLUMN categoria TEXT DEFAULT 'Geral'")
        print("Migração: Coluna 'categoria' adicionada à tabela despesas")
    
    # Atualizar registros com categoria NULL
    c.execute("UPDATE despesas SET categoria = 'Geral' WHERE categoria IS NULL OR categoria = ''")
    
    conn.commit()
    
    # Inserir dados iniciais se não existirem
    c.execute("SELECT COUNT(*) FROM clientes")
    if c.fetchone()[0] == 0:
        # Inserir administrador
        admin_senha = hashlib.md5("admin123".encode()).hexdigest()
        c.execute("INSERT INTO clientes (nome, email, senha) VALUES (?, ?, ?)",
                 ("Administrador", "admin@fundo.com", admin_senha))
        
        # Inserir configurações iniciais
        c.execute("INSERT INTO configuracoes_fundo (id, data_inicio) VALUES (1, ?)",
                 (datetime.now().strftime('%Y-%m-%d'),))
        
        conn.commit()
    
    # Inserir configuração padrão de automação se não existir
    c.execute("SELECT COUNT(*) FROM configuracoes_automacao WHERE id = 1")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO configuracoes_automacao (id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) VALUES (1, 1, '', 24)")
        conn.commit()
    
    return conn

# Inicializar banco de dados
conn = init_database()

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def verificar_login(email, senha):
    c = conn.cursor()
    senha_hash = hash_password(senha)
    c.execute("SELECT id, nome FROM clientes WHERE email = ? AND senha = ?", (email, senha_hash))
    result = c.fetchone()
    return result

def is_admin(user_id):
    return user_id == 1

def get_octav_updater():
    """Inicializa o atualizador Octav com configurações dinâmicas"""
    api_token, wallet_address = get_octav_config()
    octav_api = OctavAPI(api_token, wallet_address)
    return FundAUMUpdater('fundo_usdt.db', octav_api)

def show_octav_integration_section():
    """Mostra seção de integração com Octav na área administrativa"""
    st.subheader("🔄 Integração Octav.fi & Backup")
    
    # Criar abas para organizar melhor
    tab1, tab2, tab3 = st.tabs(["🔄 Atualização AUM", "💾 Backup", "⚙️ Configurações"])
    
    with tab1:
        # Verificar configuração de automação
        c = conn.cursor()
        c.execute("SELECT atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas FROM configuracoes_automacao WHERE id = 1")
        config_auto = c.fetchone()
        
        if not config_auto:
            # Criar configuração padrão se não existir
            c.execute("INSERT INTO configuracoes_automacao (id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) VALUES (1, 1, '', 24)")
            conn.commit()
            config_auto = (1, '', 24)
        
        ativa, ultima_atualizacao, intervalo_horas = config_auto
        
        # Seção de configurações de automação
        st.write("### ⚙️ Configurações de Automação")
        
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            nova_ativa = st.toggle("🔄 Atualização Automática Diária", value=bool(ativa))
            
            if nova_ativa != bool(ativa):
                c.execute("UPDATE configuracoes_automacao SET atualizacao_automatica_ativa = ? WHERE id = 1", (nova_ativa,))
                conn.commit()
                st.success("✅ Configuração de automação atualizada!")
                st.rerun()
        
        with col_config2:
            if nova_ativa:
                st.success("🟢 **Automação ATIVA** - AUM será atualizado automaticamente")
                if ultima_atualizacao:
                    try:
                        ultima_data = datetime.fromisoformat(ultima_atualizacao)
                        st.info(f"🕐 Última atualização: {ultima_data.strftime('%d/%m/%Y %H:%M')}")
                    except:
                        st.info("🕐 Última atualização: Não disponível")
            else:
                st.warning("🔴 **Automação DESATIVADA** - Atualizações apenas manuais")
        
        st.divider()
        
        # Seção principal
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Obter configurações atuais
            api_token, wallet_address = get_octav_config()
            
            st.info("**Atualização do AUM via API Octav.fi**")
            st.write(f"**Wallet monitorada:** `{wallet_address}`")
            
            # Mostrar informações da última atualização
            updater = get_octav_updater()
            last_update = updater.get_last_update_info()
            
            if last_update:
                st.write("**Última atualização:**")
                status_color = "🟢" if last_update['status'] == 'SUCESSO' else "🔴"
                st.write(f"{status_color} {last_update['timestamp']} - ${last_update['valor']:,.2f} USD")
                st.write(f"*AUM atualizado automaticamente via Octav API. Valor da cota: {last_update.get('valor_cota', 'N/A')}*")
            else:
                st.write("⚪ Nenhuma atualização realizada ainda")
        
        with col2:
            st.write("**Ações:**")
            
            # Botão para atualização manual
            if st.button("🔄 Atualizar AUM Agora", type="primary"):
                with st.spinner("Buscando dados da Octav.fi..."):
                    updater = get_octav_updater()
                    success, message, data = updater.update_aum_from_octav()
                    
                    if success:
                        st.success(message)
                        if data:
                            st.json(data)
                            # Atualizar timestamp da última atualização automática se automação estiver ativa
                            if nova_ativa:
                                c.execute("UPDATE configuracoes_automacao SET ultima_atualizacao_automatica = ? WHERE id = 1", 
                                         (datetime.now().isoformat(),))
                                conn.commit()
                            st.rerun()
                    else:
                        st.error(message)
            
            # Botão para verificar se precisa atualizar
            if st.button("📊 Verificar Status"):
                aum_hoje = verificar_aum_atualizado()
                
                if aum_hoje:
                    st.success("✅ AUM já foi atualizado hoje")
                else:
                    st.warning("⚠️ AUM precisa ser atualizado hoje")
    
    with tab2:
        st.write("### 💾 Sistema de Backup")
        
        # Configurações de backup
        backup_ativo, ultimo_backup, intervalo_backup = get_backup_config()
        
        col_backup1, col_backup2 = st.columns(2)
        
        with col_backup1:
            novo_backup_ativo = st.toggle("💾 Backup Automático Diário", value=bool(backup_ativo))
            
            if novo_backup_ativo != bool(backup_ativo):
                c = conn.cursor()
                c.execute("UPDATE configuracoes_backup SET backup_automatico_ativo = ? WHERE id = 1", (novo_backup_ativo,))
                conn.commit()
                st.success("✅ Configuração de backup atualizada!")
                st.rerun()
        
        with col_backup2:
            if novo_backup_ativo:
                st.success("🟢 **Backup Automático ATIVO**")
                if ultimo_backup:
                    try:
                        ultima_data = datetime.fromisoformat(ultimo_backup)
                        st.info(f"🕐 Último backup: {ultima_data.strftime('%d/%m/%Y %H:%M')}")
                    except:
                        st.info("🕐 Último backup: Não disponível")
            else:
                st.warning("🔴 **Backup Automático DESATIVADO**")
        
        st.divider()
        
        # Ações de backup
        col_backup_acao1, col_backup_acao2 = st.columns(2)
        
        with col_backup_acao1:
            if st.button("💾 Fazer Backup Agora", type="primary"):
                with st.spinner("Criando backup..."):
                    sucesso, arquivo, tamanho, backup_content = realizar_backup('manual')
                    
                    if sucesso:
                        st.success(f"✅ Backup criado: {arquivo}")
                        st.info(f"📊 Tamanho: {tamanho:,} bytes")
                        
                        # Botão de download do backup
                        st.download_button(
                            label="📥 Download Backup",
                            data=backup_content,
                            file_name=arquivo,
                            mime="application/octet-stream",
                            type="secondary"
                        )
                        
                        # Atualizar último backup se automático estiver ativo
                        if novo_backup_ativo:
                            c = conn.cursor()
                            c.execute("UPDATE configuracoes_backup SET ultimo_backup_automatico = ? WHERE id = 1",
                                     (datetime.now().isoformat(),))
                            conn.commit()
                        st.rerun()
                    else:
                        st.error("❌ Erro ao criar backup")
        
        with col_backup_acao2:
            # Upload de backup
            uploaded_file = st.file_uploader("📤 Restaurar Backup", type=['db'])
            if uploaded_file is not None:
                if st.button("🔄 Restaurar Backup", type="secondary"):
                    try:
                        # Salvar arquivo temporário
                        with open("temp_backup.db", "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        
                        # Fazer backup do atual antes de restaurar
                        realizar_backup('pre_restore')
                        
                        # Restaurar backup
                        import shutil
                        shutil.copy2("temp_backup.db", "fundo_usdt.db")
                        
                        st.success("✅ Backup restaurado com sucesso!")
                        st.warning("🔄 Recarregue a página para ver as alterações")
                        
                    except Exception as e:
                        st.error(f"❌ Erro ao restaurar backup: {str(e)}")
        
        # Histórico de backups
        st.write("### 📋 Histórico de Backups")
        
        # Seção para download do banco atual
        col_download1, col_download2 = st.columns([2, 1])
        
        with col_download1:
            st.info("**💾 Download do Banco Atual**")
            st.write("Baixe uma cópia do banco de dados atual sem criar backup no histórico")
        
        with col_download2:
            # Botão para download direto do banco atual
            try:
                with open('fundo_usdt.db', 'rb') as f:
                    db_content = f.read()
                
                timestamp_atual = datetime.now().strftime('%Y%m%d_%H%M%S')
                nome_arquivo = f"fundo_usdt_atual_{timestamp_atual}.db"
                
                st.download_button(
                    label="📥 Download Banco Atual",
                    data=db_content,
                    file_name=nome_arquivo,
                    mime="application/octet-stream",
                    type="primary",
                    help="Download direto do banco de dados atual"
                )
            except Exception as e:
                st.error(f"Erro ao preparar download: {str(e)}")
        
        st.divider()
        
        # Histórico de backups realizados
        c = conn.cursor()
        c.execute("""
            SELECT timestamp, tipo, arquivo, tamanho, status, erro
            FROM historico_backups 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        backups = c.fetchall()
        
        if backups:
            st.write("**📋 Últimos Backups Realizados:**")
            backups_df = pd.DataFrame(backups, columns=[
                'Timestamp', 'Tipo', 'Arquivo', 'Tamanho (bytes)', 'Status', 'Erro'
            ])
            st.dataframe(backups_df, use_container_width=True)
            
            st.info("💡 **Como resgatar backups:** Use o botão '📥 Download Banco Atual' acima para baixar o estado atual do banco, ou faça um novo backup manual que será baixado automaticamente.")
        else:
            st.info("Nenhum backup encontrado no histórico")
    
    with tab3:
        st.write("### ⚙️ Configurações da API Octav.fi")
        
        # Obter configurações atuais
        api_token, wallet_address = get_octav_config()
        
        with st.form("config_octav_form"):
            st.write("**Configurações Atuais:**")
            
            novo_token = st.text_input(
                "🔑 Token da API Octav.fi", 
                value=api_token,
                type="password",
                help="Token JWT para autenticação na API Octav.fi"
            )
            
            nova_wallet = st.text_input(
                "👛 Endereço da Wallet", 
                value=wallet_address,
                help="Endereço da wallet a ser monitorada (formato: 0x...)"
            )
            
            submitted = st.form_submit_button("💾 Salvar Configurações", type="primary")
            
            if submitted:
                if novo_token and nova_wallet:
                    # Validar formato da wallet
                    if nova_wallet.startswith('0x') and len(nova_wallet) == 42:
                        update_octav_config(novo_token, nova_wallet)
                        st.success("✅ Configurações atualizadas com sucesso!")
                        st.info("🔄 As novas configurações serão usadas na próxima atualização")
                        st.rerun()
                    else:
                        st.error("❌ Formato de wallet inválido. Use o formato: 0x...")
                else:
                    st.error("❌ Preencha todos os campos")
        
        st.divider()
        
        # Seção de logs
        st.write("### 📊 Logs de Atualização")
        
        c = conn.cursor()
        c.execute("""
            SELECT timestamp, tipo, fonte, valor, status, detalhes, erro
            FROM logs_aum 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        logs = c.fetchall()
        
        if logs:
            logs_df = pd.DataFrame(logs, columns=[
                'Timestamp', 'Tipo', 'Fonte', 'Valor', 'Status', 'Detalhes', 'Erro'
            ])
            st.dataframe(logs_df, use_container_width=True)
        else:
            st.info("Nenhum log encontrado")

def admin_dashboard():
    st.title("⚙️ Área Administrativa")
    
    # Sidebar com informações do admin
    with st.sidebar:
        st.success(f"👤 Administrador")
        st.info(f"📧 {st.session_state.user_email}")
        if st.button("🚪 Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Tabs principais
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "AUM Diário", "Clientes", "Despesas", "Movimentações", 
        "⚠️ Gerenciamento", "🔧 Configurações", "🔄 Octav API"
    ])
    
    with tab1:
        show_aum_section()
    
    with tab2:
        show_clients_section()
    
    with tab3:
        show_expenses_section()
    
    with tab4:
        show_movements_section()
    
    with tab5:
        show_management_section()
    
    with tab6:
        show_settings_section()
    
    with tab7:
        show_octav_integration_section()

def show_aum_section():
    st.subheader("📊 Atualização de AUM")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Formulário para atualização manual
        st.write("**Atualização Manual:**")
        
        data_input = st.date_input("Data", value=datetime.now())
        valor_aum = st.number_input("Valor Total AUM (USD)", min_value=0.0, step=1000.0)
        despesas = st.number_input("Despesas (USD)", min_value=0.0, step=100.0)
        
        if st.button("Atualizar AUM"):
            if valor_aum > 0:
                # Calcular valor da cota
                c = conn.cursor()
                c.execute("SELECT SUM(cotas) FROM clientes WHERE id > 1")
                total_cotas = c.fetchone()[0] or 1
                
                valor_cota = (valor_aum - despesas) / total_cotas
                
                # Inserir no banco
                c.execute("""INSERT OR REPLACE INTO aum_diario 
                           (data, valor_total, valor_cota, despesas) 
                           VALUES (?, ?, ?, ?)""",
                         (data_input.strftime('%Y-%m-%d'), valor_aum, valor_cota, despesas))
                
                # Log da atualização manual
                c.execute("""INSERT INTO logs_aum 
                           (timestamp, tipo, fonte, valor, status, detalhes) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                         (datetime.now().isoformat(), 'ATUALIZACAO_MANUAL', 'ADMIN_INTERFACE', 
                          valor_aum, 'SUCESSO', f'AUM atualizado manualmente. Valor da cota: {valor_cota:.4f}'))
                
                conn.commit()
                st.success(f"AUM atualizado! Valor da cota: ${valor_cota:.4f}")
                st.rerun()
            else:
                st.error("Valor do AUM deve ser maior que zero")
    
    with col2:
        # Histórico AUM
        st.write("**Histórico AUM Completo**")
        
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM aum_diario")
        total_registros = c.fetchone()[0]
        st.write(f"Total de registros: {total_registros}")
        
        mostrar_completo = st.checkbox("Mostrar histórico completo")
        
        if mostrar_completo or total_registros <= 20:
            c.execute("""SELECT data, valor_total, valor_cota, despesas 
                        FROM aum_diario ORDER BY data DESC""")
        else:
            c.execute("""SELECT data, valor_total, valor_cota, despesas 
                        FROM aum_diario ORDER BY data DESC LIMIT 20""")
        
        dados = c.fetchall()
        
        if dados:
            df = pd.DataFrame(dados, columns=['Data', 'Valor Total', 'Valor Cota', 'Despesas'])
            df['Valor Total'] = df['Valor Total'].apply(lambda x: f"US$ {x:,.2f}")
            df['Valor Cota'] = df['Valor Cota'].apply(lambda x: f"US$ {x:.4f}")
            df['Despesas'] = df['Despesas'].apply(lambda x: f"US$ {x:.2f}")
            
            st.dataframe(df, use_container_width=True)
            
            # Gráfico de evolução
            if len(dados) > 1:
                df_plot = pd.DataFrame(dados, columns=['Data', 'Valor Total', 'Valor Cota', 'Despesas'])
                df_plot['Data'] = pd.to_datetime(df_plot['Data'])
                
                fig = make_subplots(
                    rows=2, cols=1,
                    subplot_titles=('Evolução do AUM Total', 'Evolução do Valor da Cota'),
                    vertical_spacing=0.1
                )
                
                fig.add_trace(
                    go.Scatter(x=df_plot['Data'], y=df_plot['Valor Total'], 
                             name='AUM Total', line=dict(color='blue')),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Scatter(x=df_plot['Data'], y=df_plot['Valor Cota'], 
                             name='Valor da Cota', line=dict(color='green')),
                    row=2, col=1
                )
                
                fig.update_layout(height=500, showlegend=False)
                fig.update_yaxes(title_text="USD", row=1, col=1)
                fig.update_yaxes(title_text="USD", row=2, col=1)
                fig.update_xaxes(title_text="Data", row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)

# Continuar com as outras funções do aplicativo original...
# (As outras funções permanecem iguais ao arquivo original)

def show_clients_section():
    st.subheader("👥 Gestão de Clientes")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.write("### ➕ Cadastrar Novo Cliente")
        nome = st.text_input("Nome Completo", placeholder="Ex: João da Silva")
        email = st.text_input("Email", placeholder="Ex: joao@email.com")
        senha = st.text_input("Senha", type="password", placeholder="Mínimo 6 caracteres")
        
        if st.button("➕ Cadastrar Cliente"):
            if nome and email and senha and len(senha) >= 6:
                try:
                    c = conn.cursor()
                    senha_hash = hash_password(senha)
                    c.execute("INSERT INTO clientes (nome, email, senha) VALUES (?, ?, ?)",
                             (nome, email, senha_hash))
                    conn.commit()
                    st.success(f"Cliente {nome} cadastrado com sucesso!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Email já cadastrado!")
            else:
                st.error("Preencha todos os campos. Senha deve ter pelo menos 6 caracteres.")
    
    with col2:
        st.write("### 👥 Clientes Cadastrados")
        
        c = conn.cursor()
        c.execute("""
            SELECT c.id, c.nome, c.email, c.cotas,
                   COALESCE(aum.valor_cota, 1.0) as valor_cota,
                   (c.cotas * COALESCE(aum.valor_cota, 1.0)) as valor_total
            FROM clientes c
            LEFT JOIN (
                SELECT valor_cota FROM aum_diario ORDER BY data DESC LIMIT 1
            ) aum ON 1=1
            WHERE c.id > 1
            ORDER BY c.nome
        """)
        
        clientes = c.fetchall()
        
        if clientes:
            # Calcular rentabilidade para cada cliente
            clientes_data = []
            for cliente in clientes:
                cliente_id, nome, email, cotas, valor_cota, valor_total = cliente
                
                # Buscar aportes líquidos
                c.execute("""
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN valor ELSE -valor END), 0)
                    FROM movimentacoes WHERE cliente_id = ?
                """, (cliente_id,))
                aportes_liquidos = c.fetchone()[0]
                
                # Calcular rentabilidade
                if aportes_liquidos > 0:
                    rentabilidade = ((valor_total - aportes_liquidos) / aportes_liquidos) * 100
                else:
                    rentabilidade = 0
                
                clientes_data.append({
                    'ID': cliente_id,
                    'Nome': nome,
                    'Email': email,
                    'Cotas': f"{cotas:,.0f}",
                    'Valor Total': f"US$ {valor_total:,.2f}",
                    'Rentabilidade': f"{rentabilidade:+.2f}%",
                    'Ações': '🗑️'
                })
            
            df_clientes = pd.DataFrame(clientes_data)
            
            # Mostrar tabela
            st.dataframe(df_clientes, use_container_width=True)
            
            # Opção para excluir cliente
            st.write("**Excluir Cliente:**")
            cliente_para_excluir = st.selectbox(
                "Selecione o cliente para excluir:",
                options=[f"{c[0]} - {c[1]}" for c in clientes],
                format_func=lambda x: x.split(' - ')[1]
            )
            
            if st.button("🗑️ Excluir Cliente Selecionado", type="secondary"):
                cliente_id = int(cliente_para_excluir.split(' - ')[0])
                
                # Verificar se cliente tem movimentações
                c.execute("SELECT COUNT(*) FROM movimentacoes WHERE cliente_id = ?", (cliente_id,))
                tem_movimentacoes = c.fetchone()[0] > 0
                
                if tem_movimentacoes:
                    st.error("Não é possível excluir cliente com movimentações!")
                else:
                    c.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
                    conn.commit()
                    st.success("Cliente excluído com sucesso!")
                    st.rerun()
        else:
            st.info("Nenhum cliente cadastrado ainda.")

def show_expenses_section():
    st.subheader("💸 Gestão de Despesas")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.write("### ➕ Registrar Nova Despesa")
        data_despesa = st.date_input("Data da Despesa", value=datetime.now())
        descricao = st.text_input("Descrição", placeholder="Ex: Taxa de administração")
        valor_despesa = st.number_input("Valor (USD)", min_value=0.0, step=10.0)
        categoria = st.selectbox("Categoria", 
                                ["Administrativa", "Operacional", "Marketing", "Jurídica", "Outras"])
        
        if st.button("➕ Registrar Despesa"):
            if descricao and valor_despesa > 0:
                c = conn.cursor()
                c.execute("""INSERT INTO despesas (data, descricao, valor, categoria) 
                           VALUES (?, ?, ?, ?)""",
                         (data_despesa.strftime('%Y-%m-%d'), descricao, valor_despesa, categoria))
                conn.commit()
                st.success(f"Despesa de ${valor_despesa:.2f} registrada!")
                st.rerun()
            else:
                st.error("Preencha todos os campos!")
    
    with col2:
        st.write("### 📊 Histórico de Despesas")
        
        c = conn.cursor()
        c.execute("""SELECT data, descricao, valor, categoria 
                    FROM despesas ORDER BY data DESC LIMIT 50""")
        despesas = c.fetchall()
        
        if despesas:
            df_despesas = pd.DataFrame(despesas, 
                                     columns=['Data', 'Descrição', 'Valor', 'Categoria'])
            df_despesas['Valor'] = df_despesas['Valor'].apply(lambda x: f"US$ {x:.2f}")
            
            st.dataframe(df_despesas, use_container_width=True)
            
            # Resumo por categoria
            c.execute("""SELECT categoria, SUM(valor) as total 
                        FROM despesas GROUP BY categoria ORDER BY total DESC""")
            resumo = c.fetchall()
            
            if resumo:
                st.write("**Resumo por Categoria:**")
                df_resumo = pd.DataFrame(resumo, columns=['Categoria', 'Total'])
                
                fig = px.pie(df_resumo, values='Total', names='Categoria', 
                           title="Distribuição de Despesas por Categoria")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma despesa registrada ainda.")

def show_movements_section():
    st.subheader("💰 Todas as Movimentações")
    
    # Verificar atualização automática no início
    ativa, precisa_atualizar = verificar_configuracao_automacao()
    if ativa and precisa_atualizar:
        with st.spinner("Executando atualização automática do AUM..."):
            sucesso, mensagem = executar_atualizacao_automatica()
            if sucesso:
                st.success(f"✅ {mensagem}")
            else:
                st.warning(f"⚠️ {mensagem}")
    
    # Adicionar nova movimentação
    with st.expander("➕ Registrar Nova Movimentação"):
        # Verificar se AUM foi atualizado hoje
        aum_atualizado_hoje = verificar_aum_atualizado()
        
        if not aum_atualizado_hoje:
            st.warning("⚠️ **ATENÇÃO: O AUM precisa ser atualizado antes de registrar investimentos!**")
            st.info("📋 **Escolha uma opção para atualizar o AUM:**")
            
            col_opcao1, col_opcao2 = st.columns(2)
            
            with col_opcao1:
                if st.button("🔄 Atualização Automática (Octav API)", type="primary"):
                    with st.spinner("Atualizando AUM via Octav API..."):
                        try:
                            api_token, wallet_address = get_octav_config()
                            octav_api = OctavAPI(api_token, wallet_address)
                            updater = FundAUMUpdater('fundo_usdt.db', octav_api)
                            
                            portfolio_data = octav_api.get_historical_portfolio()
                            if portfolio_data:
                                portfolio_value = octav_api.extract_networth(portfolio_data)
                                if portfolio_value:
                                    success = updater.update_aum_from_portfolio(portfolio_value)
                                    if success:
                                        st.success(f"✅ AUM atualizado automaticamente: ${portfolio_value:,.2f}")
                                        st.rerun()
                                    else:
                                        st.error("❌ Erro ao atualizar AUM automaticamente")
                                else:
                                    st.error("❌ Erro ao extrair valor do portfólio")
                            else:
                                st.error("❌ Erro ao obter dados do portfólio")
                        except Exception as e:
                            st.error(f"❌ Erro: {str(e)}")
            
            with col_opcao2:
                if st.button("✏️ Atualização Manual"):
                    st.info("👆 Vá para a aba 'AUM Diário' para fazer atualização manual")
            
            st.divider()
            st.warning("🚫 **Registre o investimento somente após atualizar o AUM**")
            return
        
        # Mostrar status do AUM atual
        c = conn.cursor()
        c.execute("SELECT data, valor_total, valor_cota FROM aum_diario ORDER BY data DESC LIMIT 1")
        ultimo_aum = c.fetchone()
        
        if ultimo_aum:
            st.success(f"✅ **AUM Atualizado:** {ultimo_aum[0]} | Valor Total: ${ultimo_aum[1]:,.2f} | Valor da Cota: ${ultimo_aum[2]:.4f}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Buscar clientes
            c.execute("SELECT id, nome FROM clientes WHERE id > 1 ORDER BY nome")
            clientes = c.fetchall()
            
            if clientes:
                cliente_selecionado = st.selectbox(
                    "Cliente:",
                    options=clientes,
                    format_func=lambda x: x[1]
                )
                
                tipo_mov = st.selectbox("Tipo:", ["ENTRADA", "SAÍDA"])
                
        with col2:
            valor_mov = st.number_input("Valor (USD):", min_value=0.0, step=100.0)
            data_mov = st.date_input("Data:", value=datetime.now())
            
        with col3:
            descricao_mov = st.text_area("Descrição:", placeholder="Detalhes da movimentação")
            
            if st.button("➕ Registrar Movimentação"):
                if cliente_selecionado and valor_mov > 0:
                    # Buscar valor da cota atual
                    c.execute("SELECT valor_cota FROM aum_diario ORDER BY data DESC LIMIT 1")
                    valor_cota_result = c.fetchone()
                    valor_cota = valor_cota_result[0] if valor_cota_result else 1.0
                    
                    # Calcular cotas
                    if tipo_mov == "ENTRADA":
                        cotas = valor_mov / valor_cota
                    else:
                        cotas = -(valor_mov / valor_cota)
                    
                    # Inserir movimentação
                    c.execute("""INSERT INTO movimentacoes 
                               (cliente_id, tipo, valor, cotas, data, descricao) 
                               VALUES (?, ?, ?, ?, ?, ?)""",
                             (cliente_selecionado[0], tipo_mov, valor_mov, cotas, 
                              data_mov.strftime('%Y-%m-%d'), descricao_mov))
                    
                    # Atualizar cotas do cliente
                    c.execute("SELECT cotas FROM clientes WHERE id = ?", (cliente_selecionado[0],))
                    cotas_atuais = c.fetchone()[0]
                    novas_cotas = cotas_atuais + cotas
                    
                    c.execute("UPDATE clientes SET cotas = ? WHERE id = ?", 
                             (novas_cotas, cliente_selecionado[0]))
                    
                    conn.commit()
                    st.success(f"Movimentação registrada! Cotas: {cotas:+.2f}")
                    st.rerun()
                else:
                    st.error("Preencha todos os campos obrigatórios!")
    
    # Mostrar todas as movimentações
    st.write("⚠️ **Clique no botão 🗑️ para excluir uma movimentação (as cotas serão ajustadas automaticamente)**")
    
    c = conn.cursor()
    c.execute("""
        SELECT m.id, m.data, c.nome, m.tipo, m.valor, m.cotas, m.descricao
        FROM movimentacoes m
        JOIN clientes c ON m.cliente_id = c.id
        ORDER BY m.data DESC, m.id DESC
    """)
    
    movimentacoes = c.fetchall()
    
    if movimentacoes:
        for mov in movimentacoes:
            mov_id, data, cliente, tipo, valor, cotas, descricao = mov
            
            col1, col2 = st.columns([10, 1])
            
            with col1:
                # Cor baseada no tipo
                cor = "🟢" if tipo == "ENTRADA" else "🔴"
                st.write(f"{data} | {cliente} | {cor} **{tipo}** | US$ {valor:,.2f} | {cotas:,.2f} cotas | {descricao or 'cash in usdt ' + cliente.split()[0].lower()}")
            
            with col2:
                if st.button("🗑️", key=f"del_{mov_id}"):
                    # Buscar cliente da movimentação
                    c.execute("SELECT cliente_id FROM movimentacoes WHERE id = ?", (mov_id,))
                    cliente_id = c.fetchone()[0]
                    
                    # Reverter cotas do cliente
                    c.execute("SELECT cotas FROM clientes WHERE id = ?", (cliente_id,))
                    cotas_atuais = c.fetchone()[0]
                    novas_cotas = cotas_atuais - cotas
                    
                    c.execute("UPDATE clientes SET cotas = ? WHERE id = ?", (novas_cotas, cliente_id))
                    
                    # Excluir movimentação
                    c.execute("DELETE FROM movimentacoes WHERE id = ?", (mov_id,))
                    
                    conn.commit()
                    st.success("Movimentação excluída e cotas ajustadas!")
                    st.rerun()
    else:
        st.info("Nenhuma movimentação registrada ainda.")

def show_management_section():
    st.subheader("⚠️ Gerenciamento do Sistema")
    
    st.warning("**ATENÇÃO: As operações desta seção são irreversíveis!**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 🗑️ Zerar Banco de Dados")
        st.error("Esta operação irá apagar TODOS os dados do sistema!")
        
        confirmacao = st.text_input("Digite 'CONFIRMAR' para prosseguir:")
        
        if st.button("🗑️ ZERAR TUDO", type="secondary"):
            if confirmacao == "CONFIRMAR":
                c = conn.cursor()
                
                # Apagar todas as tabelas
                tabelas = ['movimentacoes', 'despesas', 'aum_diario', 'logs_aum']
                for tabela in tabelas:
                    c.execute(f"DELETE FROM {tabela}")
                
                # Manter apenas o admin
                c.execute("DELETE FROM clientes WHERE id > 1")
                
                conn.commit()
                st.success("Banco de dados zerado com sucesso!")
                st.rerun()
            else:
                st.error("Digite 'CONFIRMAR' para prosseguir")
    
    with col2:
        st.write("### 📊 Estatísticas do Banco")
        
        c = conn.cursor()
        
        # Contar registros
        tabelas_info = [
            ('Clientes', 'clientes', 'WHERE id > 1'),
            ('Movimentações', 'movimentacoes', ''),
            ('Registros AUM', 'aum_diario', ''),
            ('Despesas', 'despesas', ''),
            ('Logs AUM', 'logs_aum', '')
        ]
        
        for nome, tabela, condicao in tabelas_info:
            c.execute(f"SELECT COUNT(*) FROM {tabela} {condicao}")
            count = c.fetchone()[0]
            st.metric(nome, count)

def show_settings_section():
    st.subheader("🔧 Configurações do Fundo")
    
    c = conn.cursor()
    c.execute("SELECT * FROM configuracoes_fundo WHERE id = 1")
    config = c.fetchone()
    
    if config:
        if len(config) >= 7:
            _, nome_atual, data_inicio, valor_cota_inicial, aum_inicial = config[0:5]
        elif len(config) >= 5:
            _, nome_atual, data_inicio, valor_cota_inicial, aum_inicial = config[:5]
        else:
            nome_atual = config[1] if len(config) > 1 else "Fundo USDT"
            data_inicio = config[2] if len(config) > 2 else datetime.now().strftime('%Y-%m-%d')
            valor_cota_inicial = config[3] if len(config) > 3 else 1.0
            aum_inicial = config[4] if len(config) > 4 else 0.0
    else:
        nome_atual = "Fundo USDT"
        data_inicio = datetime.now().strftime('%Y-%m-%d')
        valor_cota_inicial = 1.0
        aum_inicial = 0.0
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### ⚙️ Configurações Gerais")
        
        nome_fundo = st.text_input("Nome do Fundo:", value=nome_atual)
        data_inicio_input = st.date_input("Data de Início:", 
                                        value=datetime.strptime(data_inicio, '%Y-%m-%d').date())
        valor_cota_inicial_input = st.number_input("Valor da Cota Inicial:", 
                                                  value=float(valor_cota_inicial), step=0.01)
        aum_inicial_input = st.number_input("AUM Inicial:", 
                                          value=float(aum_inicial), step=1000.0)
        
        if st.button("💾 Salvar Configurações"):
            c.execute("""INSERT OR REPLACE INTO configuracoes_fundo 
                        (id, nome_fundo, data_inicio, valor_cota_inicial, aum_inicial) 
                        VALUES (1, ?, ?, ?, ?)""",
                     (nome_fundo, data_inicio_input.strftime('%Y-%m-%d'), 
                      valor_cota_inicial_input, aum_inicial_input))
            conn.commit()
            st.success("Configurações salvas com sucesso!")
            st.rerun()
    
    with col2:
        st.write("### 🔐 Configurações de API")
        
        st.info("**Octav.fi API**")
        api_token, wallet_address = get_octav_config()
        st.code(f"Token: {api_token[:20]}...")
        st.code(f"Wallet: {wallet_address}")
        
        st.write("### 📊 Informações do Sistema")
        
        # Mostrar estatísticas
        c.execute("SELECT COUNT(*) FROM clientes WHERE id > 1")
        total_clientes = c.fetchone()[0]
        
        c.execute("SELECT SUM(cotas) FROM clientes WHERE id > 1")
        total_cotas = c.fetchone()[0] or 0
        
        c.execute("SELECT valor_total FROM aum_diario ORDER BY data DESC LIMIT 1")
        aum_atual_result = c.fetchone()
        aum_atual = aum_atual_result[0] if aum_atual_result else 0
        
        st.metric("Total de Clientes", total_clientes)
        st.metric("Total de Cotas", f"{total_cotas:,.0f}")
        st.metric("AUM Atual", f"US$ {aum_atual:,.2f}")

def client_dashboard(user_id, user_name):
    st.title(f"💰 Dashboard - {user_name}")
    
    # Sidebar
    with st.sidebar:
        st.success(f"👤 {user_name}")
        st.info(f"📧 {st.session_state.user_email}")
        if st.button("🚪 Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Buscar dados do cliente
    c = conn.cursor()
    
    # Informações básicas
    c.execute("SELECT cotas FROM clientes WHERE id = ?", (user_id,))
    cotas_cliente = c.fetchone()[0]
    
    # Valor atual da cota
    c.execute("SELECT valor_cota FROM aum_diario ORDER BY data DESC LIMIT 1")
    valor_cota_result = c.fetchone()
    valor_cota_atual = valor_cota_result[0] if valor_cota_result else 1.0
    
    # Valor total do investimento
    valor_total_investimento = cotas_cliente * valor_cota_atual
    
    # Aportes líquidos
    c.execute("""SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN valor ELSE -valor END), 0)
                FROM movimentacoes WHERE cliente_id = ?""", (user_id,))
    aportes_liquidos = c.fetchone()[0]
    
    # Ganho/Perda
    ganho_perda = valor_total_investimento - aportes_liquidos
    rentabilidade_pct = (ganho_perda / aportes_liquidos * 100) if aportes_liquidos > 0 else 0
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Cotas Possuídas", f"{cotas_cliente:,.2f}")
    
    with col2:
        st.metric("Valor da Cota", f"US$ {valor_cota_atual:.4f}")
    
    with col3:
        st.metric("Valor Total", f"US$ {valor_total_investimento:,.2f}")
    
    with col4:
        cor_ganho = "normal" if ganho_perda >= 0 else "inverse"
        st.metric("Ganho/Perda", f"US$ {ganho_perda:,.2f}", 
                 f"{rentabilidade_pct:+.2f}%", delta_color=cor_ganho)
    
    # Tabs do dashboard
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumo", "📈 Performance", "📊 Análise", "📋 Extrato"])
    
    with tab1:
        show_client_summary(user_id, cotas_cliente, valor_total_investimento, aportes_liquidos)
    
    with tab2:
        show_client_performance(user_id)
    
    with tab3:
        show_client_analysis()
    
    with tab4:
        show_client_statement(user_id)

def show_client_summary(user_id, cotas, valor_total, aportes_liquidos):
    st.subheader("📊 Resumo do Investimento")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de composição
        ganho_perda = valor_total - aportes_liquidos
        
        if valor_total > 0:
            dados_composicao = {
                'Categoria': ['Aportes', 'Ganhos/Perdas'],
                'Valor': [aportes_liquidos, ganho_perda]
            }
            
            fig = px.pie(dados_composicao, values='Valor', names='Categoria',
                        title="Composição do Investimento")
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Informações detalhadas
        st.write("**Detalhes do Investimento:**")
        st.write(f"• Cotas possuídas: {cotas:,.2f}")
        st.write(f"• Aportes líquidos: US$ {aportes_liquidos:,.2f}")
        st.write(f"• Valor atual: US$ {valor_total:,.2f}")
        st.write(f"• Ganho/Perda: US$ {ganho_perda:,.2f}")
        
        if aportes_liquidos > 0:
            rentabilidade = (ganho_perda / aportes_liquidos) * 100
            st.write(f"• Rentabilidade: {rentabilidade:+.2f}%")

def show_client_performance(user_id):
    st.subheader("📈 Análise de Performance")
    
    # Buscar histórico de AUM
    c = conn.cursor()
    c.execute("SELECT data, valor_cota FROM aum_diario ORDER BY data")
    historico_aum = c.fetchall()
    
    if len(historico_aum) > 1:
        df_aum = pd.DataFrame(historico_aum, columns=['Data', 'Valor_Cota'])
        df_aum['Data'] = pd.to_datetime(df_aum['Data'])
        
        # Buscar cotas do cliente ao longo do tempo
        c.execute("""
            SELECT data, 
                   SUM(CASE WHEN tipo = 'ENTRADA' THEN cotas ELSE -cotas END) OVER (ORDER BY data) as cotas_acumuladas
            FROM movimentacoes 
            WHERE cliente_id = ? 
            ORDER BY data
        """, (user_id,))
        
        movimentacoes_cliente = c.fetchall()
        
        if movimentacoes_cliente:
            df_mov = pd.DataFrame(movimentacoes_cliente, columns=['Data', 'Cotas_Acumuladas'])
            df_mov['Data'] = pd.to_datetime(df_mov['Data'])
            
            # Merge dos dados
            df_combined = pd.merge_asof(df_aum.sort_values('Data'), 
                                     df_mov.sort_values('Data'), 
                                     on='Data', direction='backward')
            
            df_combined['Cotas_Acumuladas'] = df_combined['Cotas_Acumuladas'].fillna(0)
            df_combined['Valor_Portfolio'] = df_combined['Valor_Cota'] * df_combined['Cotas_Acumuladas']
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Gráfico da evolução da cota
                fig1 = px.line(df_combined, x='Data', y='Valor_Cota',
                              title='Evolução do Valor da Cota do Fundo')
                fig1.update_yaxes(title='Valor da Cota (USD)')
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # Gráfico da evolução do patrimônio do cliente
                fig2 = px.line(df_combined, x='Data', y='Valor_Portfolio',
                              title='Evolução do Seu Patrimônio')
                fig2.update_yaxes(title='Valor do Patrimônio (USD)')
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Dados insuficientes para análise de performance.")

def show_client_analysis():
    st.subheader("📊 Análise Comparativa")
    
    # Buscar dados de rentabilidade do fundo
    c = conn.cursor()
    c.execute("SELECT data, valor_cota FROM aum_diario ORDER BY data")
    dados_cota = c.fetchall()
    
    if len(dados_cota) > 1:
        df = pd.DataFrame(dados_cota, columns=['Data', 'Valor_Cota'])
        df['Data'] = pd.to_datetime(df['Data'])
        df = df.sort_values('Data')
        
        # Calcular retornos
        df['Retorno_Diario'] = df['Valor_Cota'].pct_change()
        df['Retorno_Acumulado'] = (df['Valor_Cota'] / df['Valor_Cota'].iloc[0] - 1) * 100
        
        # Análise mensal
        df['Ano_Mes'] = df['Data'].dt.to_period('M')
        retornos_mensais = df.groupby('Ano_Mes')['Retorno_Diario'].apply(
            lambda x: (1 + x).prod() - 1
        ).reset_index()
        retornos_mensais['Retorno_Mensal_Pct'] = retornos_mensais['Retorno_Diario'] * 100
        # Converter Period para string para evitar erro de serialização JSON
        retornos_mensais['Ano_Mes_Str'] = retornos_mensais['Ano_Mes'].astype(str)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Gráfico de rentabilidade mensal
            if len(retornos_mensais) > 0:
                fig1 = px.bar(retornos_mensais, x='Ano_Mes_Str', y='Retorno_Mensal_Pct',
                             title='Rentabilidade Mensal do Fundo (%)')
                fig1.update_yaxes(title='Rentabilidade (%)')
                fig1.update_xaxes(title='Período')
                st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # Gráfico de rentabilidade acumulada
            fig2 = px.line(df, x='Data', y='Retorno_Acumulado',
                          title='Rentabilidade Acumulada do Fundo (%)')
            fig2.update_yaxes(title='Rentabilidade Acumulada (%)')
            st.plotly_chart(fig2, use_container_width=True)
        
        # Estatísticas
        st.write("### 📊 Estatísticas do Fundo")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            retorno_total = df['Retorno_Acumulado'].iloc[-1]
            st.metric("Retorno Total", f"{retorno_total:.2f}%")
        
        with col2:
            if len(retornos_mensais) > 0:
                retorno_medio_mensal = retornos_mensais['Retorno_Mensal_Pct'].mean()
                st.metric("Retorno Médio Mensal", f"{retorno_medio_mensal:.2f}%")
        
        with col3:
            volatilidade = df['Retorno_Diario'].std() * np.sqrt(252) * 100  # Anualizada
            st.metric("Volatilidade Anual", f"{volatilidade:.2f}%")
        
        with col4:
            dias_operacao = (df['Data'].iloc[-1] - df['Data'].iloc[0]).days
            st.metric("Dias de Operação", dias_operacao)
    
    else:
        st.info("Dados insuficientes para análise comparativa.")

def show_client_statement(user_id):
    st.subheader("📋 Extrato de Movimentações")
    
    c = conn.cursor()
    c.execute("""
        SELECT data, tipo, valor, cotas, descricao
        FROM movimentacoes 
        WHERE cliente_id = ? 
        ORDER BY data DESC, id DESC
    """, (user_id,))
    
    movimentacoes = c.fetchall()
    
    if movimentacoes:
        # Criar DataFrame
        df_extrato = pd.DataFrame(movimentacoes, 
                                columns=['Data', 'Tipo', 'Valor (USD)', 'Cotas', 'Descrição'])
        
        # Formatação
        df_extrato['Valor (USD)'] = df_extrato['Valor (USD)'].apply(lambda x: f"${x:,.2f}")
        df_extrato['Cotas'] = df_extrato['Cotas'].apply(lambda x: f"{x:+,.2f}")
        
        # Aplicar cores baseadas no tipo
        def highlight_tipo(row):
            if row['Tipo'] == 'ENTRADA':
                return ['background-color: #d4edda'] * len(row)
            else:
                return ['background-color: #f8d7da'] * len(row)
        
        st.dataframe(df_extrato.style.apply(highlight_tipo, axis=1), 
                    use_container_width=True)
        
        # Resumo
        st.write("### 📊 Resumo das Movimentações")
        
        total_entradas = sum(mov[2] for mov in movimentacoes if mov[1] == 'ENTRADA')
        total_saidas = sum(mov[2] for mov in movimentacoes if mov[1] == 'SAÍDA')
        saldo_liquido = total_entradas - total_saidas
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total de Aportes", f"US$ {total_entradas:,.2f}")
        
        with col2:
            st.metric("Total de Resgates", f"US$ {total_saidas:,.2f}")
        
        with col3:
            st.metric("Saldo Líquido", f"US$ {saldo_liquido:,.2f}")
    
    else:
        st.info("Nenhuma movimentação encontrada.")

def main():
    # Verificar se usuário está logado
    if 'user_id' not in st.session_state:
        show_login_page()
    else:
        # Verificar se é admin ou cliente
        if is_admin(st.session_state.user_id):
            admin_dashboard()
        else:
            client_dashboard(st.session_state.user_id, st.session_state.user_name)

def show_login_page():
    st.title("🏦 Fundo USDT - Login")
    
    st.subheader("Acesso ao Sistema")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        email = st.text_input("Email")
        senha = st.text_input("Senha", type="password")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("Entrar", type="primary"):
                if email and senha:
                    user_data = verificar_login(email, senha)
                    if user_data:
                        st.session_state.user_id = user_data[0]
                        st.session_state.user_name = user_data[1]
                        st.session_state.user_email = email
                        st.rerun()
                    else:
                        st.error("Email ou senha incorretos!")
                else:
                    st.error("Preencha todos os campos!")
        
        with col_btn2:
            if st.button("Demo"):
                st.info("**Credenciais de Demonstração:**")
                st.code("Admin: admin@fundo.com / admin123")
                st.code("Cliente: joao@email.com / demo123")
    
    with col2:
        st.info("**Sistema de Gestão de Fundo de Investimento**")
        st.write("• Dashboard completo")
        st.write("• Gestão de clientes")
        st.write("• Controle de AUM")
        st.write("• Integração Octav.fi")
        st.write("• Relatórios detalhados")

if __name__ == "__main__":
    main()

