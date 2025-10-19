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

# Função para execução segura de consultas SQL
def execute_safe_query(cursor, query, params=None):
    """
    Executa consulta SQL de forma segura, adaptando para estruturas antigas
    """
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return True
    except sqlite3.OperationalError as e:
        if "no such column" in str(e).lower():
            print(f"Adaptando consulta devido a: {e}")
            # Para consultas problemáticas, usar versão compatível
            return False
        else:
            raise e

# Configuração da página
st.set_page_config(
    page_title="Sistema Multi-Fundos USDT",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Funções auxiliares para automação
def verificar_configuracao_automacao(fundo_id):
    """Verifica se a atualização automática está ativa para um fundo específico"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    try:
        c.execute("SELECT atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas FROM configuracoes_automacao WHERE fundo_id = ?", (fundo_id,))
        config = c.fetchone()
        
        if not config:
            # Criar configuração padrão se não existir
            c.execute("INSERT OR IGNORE INTO configuracoes_automacao (fundo_id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) VALUES (?, 1, '', 24)", (fundo_id,))
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
                return True, True  # Precisa atualizar
            else:
                return True, False  # Ativo mas não precisa atualizar ainda
                
        except ValueError:
            return True, True  # Erro na data, executar atualização
    
    except sqlite3.OperationalError:
        # Tabela não existe, criar
        return True, True
    
    finally:
        conn.close()

def executar_atualizacao_automatica(fundo_id):
    """Executa a atualização automática do AUM para um fundo específico"""
    try:
        conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
        
        # Executar atualização via Octav API
        api_token, wallet_address = get_octav_config(fundo_id)
        octav_api = OctavAPI(api_token, wallet_address)
        updater = FundAUMUpdater('fundo_usdt.db', octav_api)
        
        portfolio_data = octav_api.get_historical_portfolio()
        if portfolio_data:
            portfolio_value = octav_api.extract_networth(portfolio_data)
            if portfolio_value:
                # Atualizar AUM no banco
                success, message, data = updater.update_aum_from_octav(fundo_id)
                
                if success:
                    # Atualizar timestamp da última atualização
                    c = conn.cursor()
                    c.execute("UPDATE configuracoes_automacao SET ultima_atualizacao_automatica = ? WHERE fundo_id = ?", 
                             (datetime.now().isoformat(), fundo_id))
                    conn.commit()
                    
                    return True, f"AUM atualizado automaticamente: ${portfolio_value:,.2f}"
                else:
                    return False, f"Erro na atualização automática: {message}"
            else:
                return False, "Erro ao obter valor do portfólio"
        else:
            return False, "Erro ao conectar com Octav API"
            
    except Exception as e:
        return False, f"Erro na atualização automática: {str(e)}"
    finally:
        if 'conn' in locals():
            conn.close()

# Constantes padrão (para migração)
OCTAV_API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwczovL2hhc3VyYS5pby9qd3QvY2xhaW1zIjp7IngtaGFzdXJhLWRlZmF1bHQtcm9sZSI6InVzZXIiLCJ4LWhhc3VyYS1hbGxvd2VkLXJvbGVzIjpbInVzZXIiXSwieC1oYXN1cmEtdXNlci1pZCI6InNhbnJlbW8yNjE0MSJ9fQ.0eLf5m4kQPETnUaZbN6LFMoV8hxGwjrdZ598r9o61Yc"
OCTAV_WALLET_ADDRESS = "0x3FfDb6ea2084d2BDD62F434cA6B5F610Fa2730aB"

def get_octav_config(fundo_id):
    """Obtém configurações da API Octav para um fundo específico"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    try:
        c.execute("SELECT api_token, wallet_address FROM configuracoes_octav WHERE fundo_id = ?", (fundo_id,))
        config = c.fetchone()
        
        if not config:
            # Criar configuração padrão para o fundo
            c.execute("INSERT OR IGNORE INTO configuracoes_octav (fundo_id, api_token, wallet_address) VALUES (?, ?, ?)",
                     (fundo_id, OCTAV_API_TOKEN, OCTAV_WALLET_ADDRESS))
            conn.commit()
            return OCTAV_API_TOKEN, OCTAV_WALLET_ADDRESS
        
        return config[0] or OCTAV_API_TOKEN, config[1] or OCTAV_WALLET_ADDRESS
    
    finally:
        conn.close()

def update_octav_config(fundo_id, api_token, wallet_address):
    """Atualiza configurações da API Octav para um fundo específico"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute("""INSERT OR REPLACE INTO configuracoes_octav 
                 (fundo_id, api_token, wallet_address) 
                 VALUES (?, ?, ?)""",
              (fundo_id, api_token, wallet_address))
    conn.commit()
    conn.close()

def get_backup_config():
    """Obtém configurações de backup (global)"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    try:
        c.execute("SELECT backup_automatico_ativo, ultimo_backup_automatico, intervalo_horas FROM configuracoes_backup WHERE id = 1")
        config = c.fetchone()
        
        if not config:
            # Criar configuração padrão se não existir
            c.execute("INSERT OR IGNORE INTO configuracoes_backup (id, backup_automatico_ativo, ultimo_backup_automatico, intervalo_horas) VALUES (1, 1, '', 24)")
            conn.commit()
            return True, '', 24
        
        return config
    
    finally:
        conn.close()

def realizar_backup(tipo='manual'):
    """Realiza backup do banco de dados"""
    import shutil
    import os
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_multifundos_{timestamp}.db"
        
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

# Função auxiliar para consultas compatíveis
def consulta_compativel(cursor, tabela, colunas_select, where_fundo_id=None, order_by=None, limit=None):
    """
    Executa consulta de forma compatível com estruturas antigas e novas
    """
    try:
        # Verificar se tabela tem coluna fundo_id
        cursor.execute(f"PRAGMA table_info({tabela})")
        colunas_existentes = [row[1] for row in cursor.fetchall()]
        
        # Construir query
        query = f"SELECT {colunas_select} FROM {tabela}"
        params = []
        
        if where_fundo_id is not None and 'fundo_id' in colunas_existentes:
            query += " WHERE fundo_id = ?"
            params.append(where_fundo_id)
        
        if order_by:
            query += f" ORDER BY {order_by}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query, params)
        return cursor.fetchone() if limit == 1 else cursor.fetchall()
        
    except Exception as e:
        print(f"Erro na consulta compatível: {e}")
        return None

# Conecta ao banco de dados
@st.cache_resource
def init_database():
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    # Criar tabela de fundos (nova)
    c.execute('''CREATE TABLE IF NOT EXISTS fundos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT,
        data_inicio DATE NOT NULL,
        valor_cota_inicial REAL DEFAULT 1.0,
        ativo BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Criar tabela de clientes (mantém igual - compartilhada)
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        data_cadastro DATE DEFAULT CURRENT_DATE,
        ativo BOOLEAN DEFAULT 1
    )''')
    
    # Criar tabela de movimentações (adicionar fundo_id)
    c.execute('''CREATE TABLE IF NOT EXISTS movimentacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        cliente_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        valor REAL NOT NULL,
        cotas REAL NOT NULL,
        valor_cota REAL NOT NULL,
        data DATE NOT NULL,
        observacoes TEXT,
        FOREIGN KEY (fundo_id) REFERENCES fundos (id),
        FOREIGN KEY (cliente_id) REFERENCES clientes (id)
    )''')
    
    # Criar tabela de AUM diário (adicionar fundo_id)
    c.execute('''CREATE TABLE IF NOT EXISTS aum_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        data DATE NOT NULL,
        valor REAL NOT NULL,
        valor_cota REAL NOT NULL,
        fonte TEXT DEFAULT 'manual',
        FOREIGN KEY (fundo_id) REFERENCES fundos (id),
        UNIQUE(fundo_id, data)
    )''')
    
    # Criar tabela de despesas (adicionar fundo_id)
    c.execute('''CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        data DATE NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        categoria TEXT DEFAULT 'Geral',
        FOREIGN KEY (fundo_id) REFERENCES fundos (id)
    )''')
    
    # Criar tabela de configurações do fundo (adicionar fundo_id)
    c.execute('''CREATE TABLE IF NOT EXISTS configuracoes_fundo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        data_inicio DATE NOT NULL,
        valor_cota_inicial REAL NOT NULL,
        aum_inicial REAL NOT NULL,
        taxa_administracao REAL DEFAULT 0,
        taxa_performance REAL DEFAULT 0,
        FOREIGN KEY (fundo_id) REFERENCES fundos (id),
        UNIQUE(fundo_id)
    )''')
    
    # Criar tabela de configurações de automação (adicionar fundo_id)
    c.execute('''CREATE TABLE IF NOT EXISTS configuracoes_automacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        atualizacao_automatica_ativa BOOLEAN DEFAULT 1,
        ultima_atualizacao_automatica TEXT,
        intervalo_horas INTEGER DEFAULT 24,
        FOREIGN KEY (fundo_id) REFERENCES fundos (id),
        UNIQUE(fundo_id)
    )''')
    
    # Criar tabela de configurações de backup (global)
    c.execute('''CREATE TABLE IF NOT EXISTS configuracoes_backup (
        id INTEGER PRIMARY KEY,
        backup_automatico_ativo BOOLEAN DEFAULT 1,
        ultimo_backup_automatico TEXT,
        intervalo_horas INTEGER DEFAULT 24
    )''')
    
    # Criar tabela de configurações Octav (por fundo)
    c.execute('''CREATE TABLE IF NOT EXISTS configuracoes_octav (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        api_token TEXT NOT NULL,
        wallet_address TEXT NOT NULL,
        FOREIGN KEY (fundo_id) REFERENCES fundos (id),
        UNIQUE(fundo_id)
    )''')
    
    # Criar tabela de histórico de backups (global)
    c.execute('''CREATE TABLE IF NOT EXISTS historico_backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        tipo TEXT NOT NULL,
        arquivo TEXT NOT NULL,
        tamanho INTEGER NOT NULL,
        status TEXT NOT NULL,
        erro TEXT
    )''')
    
    # Criar tabela de logs AUM (adicionar fundo_id)
    c.execute('''CREATE TABLE IF NOT EXISTS logs_aum (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fundo_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        tipo TEXT NOT NULL,
        fonte TEXT NOT NULL,
        valor REAL,
        status TEXT NOT NULL,
        detalhes TEXT,
        erro TEXT,
        FOREIGN KEY (fundo_id) REFERENCES fundos (id)
    )''')
    
    # Verificar se precisa migrar dados existentes
    c.execute("SELECT COUNT(*) FROM fundos")
    fundos_count = c.fetchone()[0]
    
    if fundos_count == 0:
        # Primeira execução - criar fundo padrão e migrar dados
        migrar_dados_existentes(c)
    
    conn.commit()
    return conn

def migrar_dados_existentes(cursor):
    """Migra dados existentes para estrutura multi-fundos"""
    
    # Criar fundo padrão (usar INSERT OR IGNORE para evitar duplicatas)
    cursor.execute("""INSERT OR IGNORE INTO fundos (id, nome, descricao, data_inicio, valor_cota_inicial, ativo) 
                     VALUES (1, 'Fundo USDT', 'Fundo principal de investimento em USDT', '2024-01-01', 1.0, 1)""")
    
    # Adicionar colunas fundo_id nas tabelas existentes se não existirem
    try:
        # Verificar e adicionar fundo_id em movimentacoes
        try:
            cursor.execute("SELECT fundo_id FROM movimentacoes LIMIT 1")
        except:
            cursor.execute("ALTER TABLE movimentacoes ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
        # Verificar e adicionar fundo_id em aum_diario
        try:
            cursor.execute("SELECT fundo_id FROM aum_diario LIMIT 1")
        except:
            cursor.execute("ALTER TABLE aum_diario ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
        # Verificar e adicionar fundo_id em despesas
        try:
            cursor.execute("SELECT fundo_id FROM despesas LIMIT 1")
        except:
            cursor.execute("ALTER TABLE despesas ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
        # Verificar e adicionar fundo_id em configuracoes_fundo
        try:
            cursor.execute("SELECT fundo_id FROM configuracoes_fundo LIMIT 1")
        except:
            cursor.execute("ALTER TABLE configuracoes_fundo ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
        # Verificar e adicionar fundo_id em configuracoes_automacao
        try:
            cursor.execute("SELECT fundo_id FROM configuracoes_automacao LIMIT 1")
        except:
            cursor.execute("ALTER TABLE configuracoes_automacao ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
        # Verificar e adicionar fundo_id em configuracoes_octav
        try:
            cursor.execute("SELECT fundo_id FROM configuracoes_octav LIMIT 1")
        except:
            cursor.execute("ALTER TABLE configuracoes_octav ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
        # Verificar e adicionar fundo_id em logs_aum
        try:
            cursor.execute("SELECT fundo_id FROM logs_aum LIMIT 1")
        except:
            cursor.execute("ALTER TABLE logs_aum ADD COLUMN fundo_id INTEGER DEFAULT 1")
            
    except Exception as e:
        print(f"Aviso ao adicionar colunas: {e}")
    
    # Inserir configurações padrão para o fundo 1 (agora que as colunas existem)
    # Verificar estrutura da tabela configuracoes_fundo antes de inserir
    try:
        cursor.execute("PRAGMA table_info(configuracoes_fundo)")
        colunas_existentes = [row[1] for row in cursor.fetchall()]
        
        if 'nome' in colunas_existentes and 'fundo_id' in colunas_existentes:
            # Nova estrutura - inserir normalmente
            cursor.execute("""INSERT OR IGNORE INTO configuracoes_fundo 
                             (fundo_id, nome, data_inicio, valor_cota_inicial, aum_inicial) 
                             VALUES (1, 'Fundo USDT', '2024-01-01', 1.0, 50000.0)""")
        else:
            # Estrutura antiga - inserir apenas se não existir dados
            cursor.execute("SELECT COUNT(*) FROM configuracoes_fundo")
            if cursor.fetchone()[0] == 0:
                # Inserir com estrutura antiga
                cursor.execute("""INSERT OR IGNORE INTO configuracoes_fundo 
                                 (nome_fundo, data_inicio, valor_cota_inicial, aum_inicial) 
                                 VALUES ('Fundo USDT', '2024-01-01', 1.0, 50000.0)""")
    except Exception as e:
        print(f"Aviso ao inserir configuracoes_fundo: {e}")
    
    # Inserir configurações de automação
    try:
        cursor.execute("""INSERT OR IGNORE INTO configuracoes_automacao 
                         (fundo_id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) 
                         VALUES (1, 1, '', 24)""")
    except Exception as e:
        print(f"Aviso ao inserir configuracoes_automacao: {e}")
    
    # Inserir configurações Octav
    try:
        cursor.execute("""INSERT OR IGNORE INTO configuracoes_octav 
                         (fundo_id, api_token, wallet_address) 
                         VALUES (1, ?, ?)""", (OCTAV_API_TOKEN, OCTAV_WALLET_ADDRESS))
    except Exception as e:
        print(f"Aviso ao inserir configuracoes_octav: {e}")
    
    # Inserir configurações de backup
    try:
        cursor.execute("""INSERT OR IGNORE INTO configuracoes_backup 
                         (id, backup_automatico_ativo, ultimo_backup_automatico, intervalo_horas) 
                         VALUES (1, 1, '', 24)""")
    except Exception as e:
        print(f"Aviso ao inserir configuracoes_backup: {e}")

# Função separada para migração (não cached)
def migrar_dados_se_necessario():
    """Migra dados existentes para estrutura multi-fundos se necessário"""
    conn = sqlite3.connect('fundo_usdt.db', check_same_thread=False)
    c = conn.cursor()
    
    try:
        # Verificar se já existe o fundo padrão
        c.execute("SELECT COUNT(*) FROM fundos WHERE id = 1")
        if c.fetchone()[0] == 0:
            migrar_dados_existentes(c)
            conn.commit()
    except Exception as e:
        print(f"Erro na migração: {e}")
    finally:
        conn.close()

# Inicializar banco
conn = init_database()

# Migrar dados se necessário (separado do cache)
migrar_dados_se_necessario()

# Funções de autenticação
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

def get_octav_updater(fundo_id):
    """Inicializa o atualizador Octav com configurações dinâmicas para um fundo"""
    api_token, wallet_address = get_octav_config(fundo_id)
    octav_api = OctavAPI(api_token, wallet_address)
    return FundAUMUpdater('fundo_usdt.db', octav_api)

# Funções de gestão de fundos
def get_fundos():
    """Retorna lista de fundos ativos"""
    c = conn.cursor()
    c.execute("SELECT id, nome, descricao, data_inicio, valor_cota_inicial, ativo FROM fundos WHERE ativo = 1 ORDER BY nome")
    return c.fetchall()

def get_fundo_by_id(fundo_id):
    """Retorna dados de um fundo específico"""
    c = conn.cursor()
    c.execute("SELECT id, nome, descricao, data_inicio, valor_cota_inicial, ativo FROM fundos WHERE id = ?", (fundo_id,))
    return c.fetchone()

def criar_novo_fundo(nome, descricao, data_inicio, valor_cota_inicial):
    """Cria um novo fundo"""
    c = conn.cursor()
    
    # NOTA: Banco de dados não tem tabela 'fundos', apenas 'configuracoes_fundo'
    # Estrutura real: id, nome_fundo, data_inicio, valor_cota_inicial, aum_inicial, moeda_base, data_criacao, data_atualizacao
    
    from datetime import datetime
    data_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Inserir novo fundo na tabela configuracoes_fundo
    c.execute("""INSERT INTO configuracoes_fundo 
                 (nome_fundo, data_inicio, valor_cota_inicial, aum_inicial, moeda_base, data_criacao, data_atualizacao) 
                 VALUES (?, ?, ?, 0.0, 'USD', ?, ?)""", 
              (nome, data_inicio, valor_cota_inicial, data_atual, data_atual))
    
    fundo_id = c.lastrowid
    
    # Criar configurações de automação (se a tabela existir)
    try:
        c.execute("""INSERT INTO configuracoes_automacao 
                     (fundo_id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) 
                     VALUES (?, 1, '', 24)""", (fundo_id,))
    except:
        pass  # Tabela pode não existir
    
    # Criar configurações Octav (se a tabela existir)
    try:
        c.execute("""INSERT INTO configuracoes_octav 
                     (fundo_id, api_token, wallet_address) 
                     VALUES (?, ?, ?)""", (fundo_id, OCTAV_API_TOKEN, OCTAV_WALLET_ADDRESS))
    except:
        pass  # Tabela pode não existir
    
    conn.commit()
    return fundo_id

def get_cliente_investimentos(cliente_id):
    """Retorna investimentos do cliente em todos os fundos"""
    c = conn.cursor()
    c.execute("""
        SELECT f.id, f.nome, 
               COALESCE(SUM(CASE WHEN m.tipo = 'ENTRADA' THEN m.cotas ELSE -m.cotas END), 0) as total_cotas,
               COALESCE(SUM(CASE WHEN m.tipo = 'ENTRADA' THEN m.valor ELSE -m.valor END), 0) as total_investido
        FROM fundos f
        LEFT JOIN movimentacoes m ON f.id = m.fundo_id AND m.cliente_id = ?
        WHERE f.ativo = 1
        GROUP BY f.id, f.nome
        HAVING total_cotas > 0
        ORDER BY f.nome
    """, (cliente_id,))
    return c.fetchall()

def get_valor_cota_atual(fundo_id):
    """Retorna o valor atual da cota de um fundo"""
    c = conn.cursor()
    c.execute("SELECT valor_cota FROM aum_diario WHERE fundo_id = ? ORDER BY data DESC LIMIT 1", (fundo_id,))
    result = c.fetchone()
    if result:
        return result[0]
    else:
        # Se não há AUM registrado, usar valor inicial
        c.execute("SELECT valor_cota_inicial FROM fundos WHERE id = ?", (fundo_id,))
        result = c.fetchone()
        return result[0] if result else 1.0

def verificar_aum_atualizado(fundo_id):
    """Verifica se o AUM foi atualizado hoje para um fundo específico"""
    c = conn.cursor()
    hoje = datetime.now().date()
    c.execute("SELECT COUNT(*) FROM aum_diario WHERE fundo_id = ? AND data = ?", (fundo_id, hoje))
    return c.fetchone()[0] > 0

# Interface principal
def main():
    # CSS customizado
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #1f77b4 0%, #17a2b8 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    .fund-selector {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        border-left: 4px solid #1f77b4;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #28a745;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header principal
    st.markdown("""
    <div class="main-header">
        <h1>🏦 Sistema Multi-Fundos USDT</h1>
        <p>Plataforma completa para gestão de múltiplos fundos de investimento</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Verificar se usuário está logado
    if 'user_id' not in st.session_state:
        login_page()
    else:
        # Verificar se é admin ou cliente
        if is_admin(st.session_state.user_id):
            admin_dashboard()
        else:
            client_dashboard(st.session_state.user_id, st.session_state.user_name)

def login_page():
    st.subheader("🔐 Login no Sistema")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            email = st.text_input("📧 Email")
            senha = st.text_input("🔒 Senha", type="password")
            submit = st.form_submit_button("🚪 Entrar", type="primary")
            
            if submit:
                if email and senha:
                    result = verificar_login(email, senha)
                    if result:
                        st.session_state.user_id = result[0]
                        st.session_state.user_name = result[1]
                        st.session_state.user_email = email
                        st.success("✅ Login realizado com sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Email ou senha incorretos")
                else:
                    st.error("❌ Preencha todos os campos")
        
        # Botão demo
        if st.button("🎭 Demo - Ver Credenciais"):
            st.info("""
            **👤 Credenciais de Demonstração:**
            
            **Administrador:**
            - Email: admin@fundo.com
            - Senha: admin123
            
            **Cliente:**
            - Email: joao@email.com  
            - Senha: demo123
            """)

def admin_dashboard():
    st.title("⚙️ Área Administrativa Multi-Fundos")
    
    # Sidebar com informações do admin
    with st.sidebar:
        st.success(f"👤 Administrador")
        st.info(f"📧 {st.session_state.user_email}")
        
        # Seletor de fundo
        st.markdown("---")
        st.subheader("🏦 Seletor de Fundo")
        
        fundos = get_fundos()
        if fundos:
            fund_options = {f"{fundo[1]}": fundo[0] for fundo in fundos}
            
            if 'selected_fund_id' not in st.session_state:
                st.session_state.selected_fund_id = fundos[0][0]  # Primeiro fundo como padrão
            
            selected_fund_name = st.selectbox(
                "Selecione o fundo:",
                options=list(fund_options.keys()),
                index=list(fund_options.values()).index(st.session_state.selected_fund_id) if st.session_state.selected_fund_id in fund_options.values() else 0
            )
            
            st.session_state.selected_fund_id = fund_options[selected_fund_name]
            
            # Mostrar info do fundo selecionado
            fundo_info = get_fundo_by_id(st.session_state.selected_fund_id)
            if fundo_info:
                st.info(f"📊 **{fundo_info[1]}**\n\n{fundo_info[2] or 'Sem descrição'}")
        else:
            st.warning("⚠️ Nenhum fundo encontrado")
            st.session_state.selected_fund_id = None
        
        st.markdown("---")
        if st.button("🚪 Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Conteúdo principal
    if st.session_state.selected_fund_id:
        # Abas principais
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "📊 Dashboard", 
            "👥 Clientes", 
            "📈 Movimentações", 
            "💰 AUM Diário", 
            "💼 Despesas", 
            "🔄 Octav API", 
            "🏦 Gestão Fundos",
            "⚙️ Configurações"
        ])
        
        with tab1:
            show_admin_dashboard(st.session_state.selected_fund_id)
        
        with tab2:
            show_clients_section()
        
        with tab3:
            show_movements_section(st.session_state.selected_fund_id)
        
        with tab4:
            show_aum_section(st.session_state.selected_fund_id)
        
        with tab5:
            show_expenses_section(st.session_state.selected_fund_id)
        
        with tab6:
            show_octav_integration_section(st.session_state.selected_fund_id)
        
        with tab7:
            show_fund_management_section()
        
        with tab8:
            show_settings_section(st.session_state.selected_fund_id)
    else:
        st.error("❌ Nenhum fundo selecionado ou disponível")

def show_fund_management_section():
    """Nova seção para gestão de fundos"""
    st.subheader("🏦 Gestão de Fundos")
    
    # Listar fundos existentes
    st.write("### 📋 Fundos Existentes")
    
    fundos = get_fundos()
    if fundos:
        fundos_df = pd.DataFrame(fundos, columns=['ID', 'Nome', 'Descrição', 'Data Início', 'Cota Inicial', 'Ativo'])
        
        # Adicionar informações extras
        for idx, row in fundos_df.iterrows():
            fundo_id = row['ID']
            
            # AUM atual - usar consulta compatível
            c = conn.cursor()
            aum_result = consulta_compativel(c, 'aum_diario', 'valor', fundo_id, 'data DESC', 1)
            aum_atual = aum_result[0][0] if aum_result else 0
            
            # Total de clientes - verificar se fundo_id existe
            try:
                c.execute("PRAGMA table_info(movimentacoes)")
                colunas_mov = [row[1] for row in c.fetchall()]
                
                if 'fundo_id' in colunas_mov:
                    c.execute("SELECT COUNT(DISTINCT cliente_id) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
                else:
                    c.execute("SELECT COUNT(DISTINCT cliente_id) FROM movimentacoes")
                
                clientes_count = c.fetchone()[0]
            except Exception as e:
                print(f"Erro ao contar clientes: {e}")
                clientes_count = 0
            
            fundos_df.loc[idx, 'AUM Atual'] = f"${aum_atual:,.2f}"
            fundos_df.loc[idx, 'Clientes'] = clientes_count
        
        st.dataframe(fundos_df, use_container_width=True)
    else:
        st.info("📝 Nenhum fundo cadastrado ainda")
    
    st.divider()
    
    # Criar novo fundo
    st.write("### ➕ Criar Novo Fundo")
    
    with st.form("criar_fundo_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome_fundo = st.text_input("📝 Nome do Fundo", placeholder="Ex: Fundo Bitcoin")
            data_inicio = st.date_input("📅 Data de Início", value=datetime.now().date())
        
        with col2:
            descricao_fundo = st.text_area("📄 Descrição", placeholder="Descrição do fundo...")
            valor_cota_inicial = st.number_input("💰 Valor da Cota Inicial", min_value=0.01, value=1.0, step=0.01)
        
        submitted = st.form_submit_button("🏦 Criar Fundo", type="primary")
        
        if submitted:
            if nome_fundo and descricao_fundo:
                try:
                    fundo_id = criar_novo_fundo(nome_fundo, descricao_fundo, data_inicio, valor_cota_inicial)
                    st.success(f"✅ Fundo '{nome_fundo}' criado com sucesso! ID: {fundo_id}")
                    st.info("🔄 Recarregue a página para ver o novo fundo na lista")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao criar fundo: {str(e)}")
            else:
                st.error("❌ Preencha todos os campos obrigatórios")

def show_admin_dashboard(fundo_id):
    """Dashboard administrativo para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    if not fundo_info:
        st.error("❌ Fundo não encontrado")
        return
    
    st.markdown(f"""
    <div class="fund-selector">
        <h3>📊 Dashboard - {fundo_info[1]}</h3>
        <p>{fundo_info[2] or 'Sem descrição'}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    c = conn.cursor()
    
    # AUM atual - usar consulta compatível
    aum_result = consulta_compativel(c, 'aum_diario', 'valor, valor_cota', fundo_id, 'data DESC', 1)
    aum_atual = aum_result[0] if aum_result else 0
    valor_cota_atual = aum_result[1] if aum_result else fundo_info[4]  # valor_cota_inicial
    
    # Total de clientes - usar consulta compatível
    try:
        c.execute("PRAGMA table_info(movimentacoes)")
        colunas_mov = [row[1] for row in c.fetchall()]
        
        if 'fundo_id' in colunas_mov:
            c.execute("SELECT COUNT(DISTINCT cliente_id) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
        else:
            c.execute("SELECT COUNT(DISTINCT cliente_id) FROM movimentacoes")
        
        total_clientes = c.fetchone()[0]
    except:
        total_clientes = 0
    
    # Total investido - usar consulta compatível
    try:
        if 'fundo_id' in colunas_mov:
            c.execute("SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN valor ELSE -valor END), 0) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
        else:
            c.execute("SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN valor ELSE -valor END), 0) FROM movimentacoes")
        
        total_investido = c.fetchone()[0]
    except:
        total_investido = 0
    
    # Total de cotas
    c.execute("SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN cotas ELSE -cotas END), 0) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
    total_cotas = c.fetchone()[0]
    
    with col1:
        st.metric("💰 AUM Atual", f"${aum_atual:,.2f}")
    
    with col2:
        st.metric("📈 Valor da Cota", f"${valor_cota_atual:.4f}")
    
    with col3:
        st.metric("👥 Total Clientes", f"{total_clientes}")
    
    with col4:
        st.metric("💼 Total Investido", f"${total_investido:,.2f}")
    
    st.divider()
    
    # Gráficos
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("📊 Evolução do AUM")
        
        # Gráfico de AUM - usar consulta compatível
        aum_data = consulta_compativel(c, 'aum_diario', 'data, valor', fundo_id, 'data')
        if not aum_data:
            aum_data = []
        
        if aum_data:
            aum_df = pd.DataFrame(aum_data, columns=['Data', 'AUM'])
            aum_df['Data'] = pd.to_datetime(aum_df['Data'])
            
            fig_aum = px.line(aum_df, x='Data', y='AUM', 
                             title='Evolução do AUM',
                             labels={'AUM': 'AUM (USD)', 'Data': 'Data'})
            fig_aum.update_layout(height=400)
            st.plotly_chart(fig_aum, use_container_width=True)
        else:
            st.info("📝 Nenhum dado de AUM disponível para este fundo")
    
    with col_chart2:
        st.subheader("📈 Evolução da Cota")
        
        if aum_data:
            cota_data = consulta_compativel(c, 'aum_diario', 'data, valor_cota', fundo_id, 'data')
            if not cota_data:
                cota_data = []
            
            if cota_data:
                cota_df = pd.DataFrame(cota_data, columns=['Data', 'Valor_Cota'])
                cota_df['Data'] = pd.to_datetime(cota_df['Data'])
                
                fig_cota = px.line(cota_df, x='Data', y='Valor_Cota',
                                  title='Evolução do Valor da Cota',
                                  labels={'Valor_Cota': 'Valor da Cota (USD)', 'Data': 'Data'})
                fig_cota.update_layout(height=400)
                st.plotly_chart(fig_cota, use_container_width=True)
        else:
            st.info("📝 Nenhum dado de cota disponível para este fundo")

def show_clients_section():
    """Seção de clientes (compartilhada entre fundos)"""
    st.subheader("👥 Gestão de Clientes")
    
    # Listar clientes
    c = conn.cursor()
    
    # Verificar estrutura da tabela clientes
    try:
        c.execute("PRAGMA table_info(clientes)")
        colunas_clientes = [row[1] for row in c.fetchall()]
        
        if 'ativo' in colunas_clientes:
            # Nova estrutura com coluna ativo
            c.execute("SELECT id, nome, email, data_cadastro, ativo FROM clientes ORDER BY nome")
            clientes = c.fetchall()
            colunas_df = ['ID', 'Nome', 'Email', 'Data Cadastro', 'Ativo']
        else:
            # Estrutura antiga sem coluna ativo
            c.execute("SELECT id, nome, email, data_cadastro FROM clientes ORDER BY nome")
            clientes = c.fetchall()
            # Adicionar coluna ativo como True por padrão
            clientes = [list(cliente) + [True] for cliente in clientes]
            colunas_df = ['ID', 'Nome', 'Email', 'Data Cadastro', 'Ativo']
            
    except Exception as e:
        print(f"Erro ao consultar clientes: {e}")
        clientes = []
        colunas_df = ['ID', 'Nome', 'Email', 'Data Cadastro', 'Ativo']
    
    if clientes:
        clientes_df = pd.DataFrame(clientes, columns=colunas_df)
        
        # Adicionar informação de investimentos por cliente
        for idx, row in clientes_df.iterrows():
            cliente_id = row['ID']
            
            # Total investido em todos os fundos
            c.execute("""SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN valor ELSE -valor END), 0) 
                        FROM movimentacoes WHERE cliente_id = ?""", (cliente_id,))
            total_investido = c.fetchone()[0]
            
            # Número de fundos que o cliente investe
            c.execute("""SELECT COUNT(DISTINCT fundo_id) FROM movimentacoes 
                        WHERE cliente_id = ? AND 
                        (SELECT SUM(CASE WHEN tipo = 'ENTRADA' THEN cotas ELSE -cotas END) 
                         FROM movimentacoes m2 WHERE m2.cliente_id = ? AND m2.fundo_id = movimentacoes.fundo_id) > 0""", 
                     (cliente_id, cliente_id))
            fundos_investidos = c.fetchone()[0]
            
            clientes_df.loc[idx, 'Total Investido'] = f"${total_investido:,.2f}"
            clientes_df.loc[idx, 'Fundos'] = fundos_investidos
        
        st.dataframe(clientes_df, use_container_width=True)
    else:
        st.info("📝 Nenhum cliente cadastrado")
    
    st.divider()
    
    # Cadastrar novo cliente
    st.write("### ➕ Cadastrar Novo Cliente")
    
    with st.form("cadastro_cliente_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nome_cliente = st.text_input("👤 Nome Completo")
            email_cliente = st.text_input("📧 Email")
        
        with col2:
            senha_cliente = st.text_input("🔒 Senha", type="password")
            confirmar_senha = st.text_input("🔒 Confirmar Senha", type="password")
        
        submitted = st.form_submit_button("👥 Cadastrar Cliente", type="primary")
        
        if submitted:
            if nome_cliente and email_cliente and senha_cliente and confirmar_senha:
                if senha_cliente == confirmar_senha:
                    try:
                        senha_hash = hash_password(senha_cliente)
                        c.execute("INSERT INTO clientes (nome, email, senha) VALUES (?, ?, ?)",
                                 (nome_cliente, email_cliente, senha_hash))
                        conn.commit()
                        st.success(f"✅ Cliente '{nome_cliente}' cadastrado com sucesso!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("❌ Email já cadastrado no sistema")
                    except Exception as e:
                        st.error(f"❌ Erro ao cadastrar cliente: {str(e)}")
                else:
                    st.error("❌ Senhas não coincidem")
            else:
                st.error("❌ Preencha todos os campos")

def show_movements_section(fundo_id):
    """Seção de movimentações para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    st.subheader(f"📈 Movimentações - {fundo_info[1]}")
    
    # Verificar se AUM está atualizado
    aum_atualizado = verificar_aum_atualizado(fundo_id)
    
    if not aum_atualizado:
        st.warning(f"⚠️ **AUM não foi atualizado hoje para o fundo {fundo_info[1]}**")
        st.info("Para registrar investimentos com precisão, é recomendado atualizar o AUM primeiro.")
        
        col_opcao1, col_opcao2 = st.columns(2)
        
        with col_opcao1:
            if st.button("🔄 Atualização Automática (Octav API)", type="primary"):
                with st.spinner("Atualizando AUM via Octav API..."):
                    try:
                        api_token, wallet_address = get_octav_config(fundo_id)
                        octav_api = OctavAPI(api_token, wallet_address)
                        updater = FundAUMUpdater('fundo_usdt.db', octav_api)
                        
                        portfolio_data = octav_api.get_historical_portfolio()
                        if portfolio_data:
                            portfolio_value = octav_api.extract_networth(portfolio_data)
                            if portfolio_value:
                                success, message, data = updater.update_aum_from_octav(fundo_id)
                                
                                if success:
                                    st.success(f"✅ AUM atualizado: ${portfolio_value:,.2f}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Erro: {message}")
                            else:
                                st.error("❌ Erro ao obter valor do portfólio")
                        else:
                            st.error("❌ Erro ao conectar com Octav API")
                    except Exception as e:
                        st.error(f"❌ Erro: {str(e)}")
        
        with col_opcao2:
            if st.button("✏️ Atualização Manual", type="secondary"):
                st.info("👆 Vá para a aba 'AUM Diário' para atualizar manualmente")
        
        st.divider()
    
    # Listar movimentações - verificar estrutura das tabelas
    c = conn.cursor()
    
    try:
        # Verificar estrutura da tabela movimentacoes
        c.execute("PRAGMA table_info(movimentacoes)")
        colunas_mov = [row[1] for row in c.fetchall()]
        
        # Construir query baseada nas colunas disponíveis
        if 'valor_cota' in colunas_mov and 'fundo_id' in colunas_mov:
            # Nova estrutura completa
            c.execute("""SELECT m.id, c.nome, m.tipo, m.valor, m.cotas, m.valor_cota, m.data, m.observacoes
                         FROM movimentacoes m
                         JOIN clientes c ON m.cliente_id = c.id
                         WHERE m.fundo_id = ?
                         ORDER BY m.data DESC, m.id DESC
                         LIMIT 50""", (fundo_id,))
            colunas_df = ['ID', 'Cliente', 'Tipo', 'Valor (USD)', 'Cotas', 'Valor da Cota', 'Data', 'Observações']
            
        elif 'fundo_id' in colunas_mov:
            # Estrutura com fundo_id mas sem valor_cota
            c.execute("""SELECT m.id, c.nome, m.tipo, m.valor, m.cotas, m.data, m.observacoes
                         FROM movimentacoes m
                         JOIN clientes c ON m.cliente_id = c.id
                         WHERE m.fundo_id = ?
                         ORDER BY m.data DESC, m.id DESC
                         LIMIT 50""", (fundo_id,))
            movimentacoes_raw = c.fetchall()
            # Adicionar valor_cota calculado (valor/cotas) ou 1.0 por padrão
            movimentacoes = []
            for mov in movimentacoes_raw:
                mov_list = list(mov)
                valor_cota_calc = mov[3] / mov[4] if mov[4] > 0 else 1.0  # valor/cotas
                mov_list.insert(5, valor_cota_calc)  # Inserir valor_cota na posição 5
                movimentacoes.append(tuple(mov_list))
            colunas_df = ['ID', 'Cliente', 'Tipo', 'Valor (USD)', 'Cotas', 'Valor da Cota', 'Data', 'Observações']
            
        else:
            # Estrutura antiga sem fundo_id
            c.execute("""SELECT m.id, c.nome, m.tipo, m.valor, m.cotas, m.data, m.observacoes
                         FROM movimentacoes m
                         JOIN clientes c ON m.cliente_id = c.id
                         ORDER BY m.data DESC, m.id DESC
                         LIMIT 50""")
            movimentacoes_raw = c.fetchall()
            # Adicionar valor_cota calculado
            movimentacoes = []
            for mov in movimentacoes_raw:
                mov_list = list(mov)
                valor_cota_calc = mov[3] / mov[4] if mov[4] > 0 else 1.0
                mov_list.insert(5, valor_cota_calc)
                movimentacoes.append(tuple(mov_list))
            colunas_df = ['ID', 'Cliente', 'Tipo', 'Valor (USD)', 'Cotas', 'Valor da Cota', 'Data', 'Observações']
            
    except Exception as e:
        print(f"Erro ao consultar movimentações: {e}")
        movimentacoes = []
        colunas_df = ['ID', 'Cliente', 'Tipo', 'Valor (USD)', 'Cotas', 'Valor da Cota', 'Data', 'Observações']
    
    # Se não foi definido movimentacoes ainda, buscar resultado da query
    if 'movimentacoes' not in locals() or movimentacoes is None:
        try:
            movimentacoes = c.fetchall()
        except:
            movimentacoes = []
    
    if movimentacoes:
        st.write("### 📋 Últimas Movimentações")
        movimentacoes_df = pd.DataFrame(movimentacoes, columns=colunas_df)
        st.dataframe(movimentacoes_df, use_container_width=True)
    else:
        st.info("📝 Nenhuma movimentação registrada para este fundo")
    
    st.divider()
    
    # Registrar nova movimentação
    st.write("### ➕ Registrar Nova Movimentação")
    
    # Listar clientes - verificar se coluna ativo existe
    try:
        c.execute("PRAGMA table_info(clientes)")
        colunas_clientes = [row[1] for row in c.fetchall()]
        
        if 'ativo' in colunas_clientes:
            c.execute("SELECT id, nome FROM clientes WHERE ativo = 1 ORDER BY nome")
        else:
            c.execute("SELECT id, nome FROM clientes ORDER BY nome")
        
        clientes = c.fetchall()
    except Exception as e:
        print(f"Erro ao consultar clientes: {e}")
        clientes = []
    
    if not clientes:
        st.warning("⚠️ Nenhum cliente cadastrado. Cadastre clientes primeiro.")
        return
    
    with st.form("movimentacao_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            cliente_options = {f"{cliente[1]}": cliente[0] for cliente in clientes}
            cliente_selecionado = st.selectbox("👤 Cliente", options=list(cliente_options.keys()))
            cliente_id = cliente_options[cliente_selecionado]
            
            tipo_movimentacao = st.selectbox("📊 Tipo", ["ENTRADA", "SAÍDA"])
        
        with col2:
            valor_movimentacao = st.number_input("💰 Valor (USD)", min_value=0.01, step=0.01)
            data_movimentacao = st.date_input("📅 Data", value=datetime.now().date())
        
        with col3:
            # Obter valor da cota atual
            valor_cota_atual = get_valor_cota_atual(fundo_id)
            st.info(f"💎 Valor da cota atual: ${valor_cota_atual:.4f}")
            
            # Calcular cotas automaticamente
            if valor_movimentacao > 0:
                cotas_calculadas = valor_movimentacao / valor_cota_atual
                st.info(f"📊 Cotas calculadas: {cotas_calculadas:.6f}")
            
            observacoes = st.text_area("📝 Observações", height=100)
        
        submitted = st.form_submit_button("💼 Registrar Movimentação", type="primary")
        
        if submitted:
            if valor_movimentacao > 0:
                try:
                    cotas = valor_movimentacao / valor_cota_atual
                    
                    c.execute("""INSERT INTO movimentacoes 
                                (fundo_id, cliente_id, tipo, valor, cotas, valor_cota, data, observacoes)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                             (fundo_id, cliente_id, tipo_movimentacao, valor_movimentacao, 
                              cotas, valor_cota_atual, data_movimentacao, observacoes))
                    conn.commit()
                    
                    st.success(f"✅ Movimentação registrada com sucesso!")
                    st.info(f"📊 {cotas:.6f} cotas de {tipo_movimentacao.lower()} para {cliente_selecionado}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao registrar movimentação: {str(e)}")
            else:
                st.error("❌ Valor deve ser maior que zero")

def show_aum_section(fundo_id):
    """Seção de AUM para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    st.subheader(f"💰 AUM Diário - {fundo_info[1]}")
    
    # Listar AUM histórico - usar consulta compatível
    c = conn.cursor()
    aum_historico = consulta_compativel(c, 'aum_diario', 'data, valor, valor_cota, fonte', fundo_id, 'data DESC', 30)
    if not aum_historico:
        aum_historico = []
    
    if aum_historico:
        st.write("### 📊 Histórico Recente")
        aum_df = pd.DataFrame(aum_historico, columns=['Data', 'AUM (USD)', 'Valor da Cota', 'Fonte'])
        st.dataframe(aum_df, use_container_width=True)
        
        # Gráfico
        aum_chart_df = pd.DataFrame(aum_historico, columns=['Data', 'AUM', 'Valor_Cota', 'Fonte'])
        aum_chart_df['Data'] = pd.to_datetime(aum_chart_df['Data'])
        
        fig = px.line(aum_chart_df, x='Data', y='AUM', 
                     title=f'Evolução do AUM - {fundo_info[1]}',
                     labels={'AUM': 'AUM (USD)', 'Data': 'Data'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📝 Nenhum registro de AUM para este fundo")
    
    st.divider()
    
    # Registrar AUM manual
    st.write("### ➕ Registrar AUM Manual")
    
    with st.form("aum_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            data_aum = st.date_input("📅 Data", value=datetime.now().date())
            valor_aum = st.number_input("💰 Valor do AUM (USD)", min_value=0.01, step=0.01)
        
        with col2:
            # Calcular valor da cota baseado no AUM e total de cotas
            c.execute("SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN cotas ELSE -cotas END), 0) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
            total_cotas = c.fetchone()[0]
            
            if total_cotas > 0 and valor_aum > 0:
                valor_cota_calculado = valor_aum / total_cotas
                st.info(f"📊 Valor da cota calculado: ${valor_cota_calculado:.6f}")
                st.info(f"📈 Total de cotas em circulação: {total_cotas:.6f}")
            else:
                valor_cota_calculado = fundo_info[4]  # valor_cota_inicial
                st.warning("⚠️ Sem cotas em circulação. Usando valor inicial da cota.")
        
        submitted = st.form_submit_button("💾 Registrar AUM", type="primary")
        
        if submitted:
            if valor_aum > 0:
                try:
                    c.execute("""INSERT OR REPLACE INTO aum_diario 
                                (fundo_id, data, valor, valor_cota, fonte)
                                VALUES (?, ?, ?, ?, 'manual')""",
                             (fundo_id, data_aum, valor_aum, valor_cota_calculado))
                    conn.commit()
                    
                    st.success(f"✅ AUM registrado com sucesso!")
                    st.info(f"💰 AUM: ${valor_aum:,.2f} | 📊 Valor da Cota: ${valor_cota_calculado:.6f}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao registrar AUM: {str(e)}")
            else:
                st.error("❌ Valor do AUM deve ser maior que zero")

def show_expenses_section(fundo_id):
    """Seção de despesas para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    st.subheader(f"💼 Despesas - {fundo_info[1]}")
    
    # Listar despesas - verificar estrutura da tabela
    c = conn.cursor()
    
    try:
        # Verificar estrutura da tabela despesas
        c.execute("PRAGMA table_info(despesas)")
        colunas_despesas = [row[1] for row in c.fetchall()]
        
        # Construir query baseada nas colunas disponíveis
        if 'categoria' in colunas_despesas and 'fundo_id' in colunas_despesas:
            # Nova estrutura completa
            c.execute("SELECT data, descricao, valor, categoria FROM despesas WHERE fundo_id = ? ORDER BY data DESC LIMIT 50", (fundo_id,))
            colunas_df = ['Data', 'Descrição', 'Valor (USD)', 'Categoria']
            
        elif 'fundo_id' in colunas_despesas:
            # Estrutura com fundo_id mas sem categoria
            c.execute("SELECT data, descricao, valor FROM despesas WHERE fundo_id = ? ORDER BY data DESC LIMIT 50", (fundo_id,))
            despesas_raw = c.fetchall()
            # Adicionar categoria padrão "Geral"
            despesas = [list(despesa) + ['Geral'] for despesa in despesas_raw]
            colunas_df = ['Data', 'Descrição', 'Valor (USD)', 'Categoria']
            
        elif 'categoria' in colunas_despesas:
            # Estrutura antiga com categoria mas sem fundo_id
            c.execute("SELECT data, descricao, valor, categoria FROM despesas ORDER BY data DESC LIMIT 50")
            despesas = c.fetchall()
            colunas_df = ['Data', 'Descrição', 'Valor (USD)', 'Categoria']
            
        else:
            # Estrutura muito antiga sem categoria nem fundo_id
            c.execute("SELECT data, descricao, valor FROM despesas ORDER BY data DESC LIMIT 50")
            despesas_raw = c.fetchall()
            # Adicionar categoria padrão "Geral"
            despesas = [list(despesa) + ['Geral'] for despesa in despesas_raw]
            colunas_df = ['Data', 'Descrição', 'Valor (USD)', 'Categoria']
            
    except Exception as e:
        print(f"Erro ao consultar despesas: {e}")
        despesas = []
        colunas_df = ['Data', 'Descrição', 'Valor (USD)', 'Categoria']
    
    # Se não foi definido despesas ainda, buscar resultado da query
    if 'despesas' not in locals() or despesas is None:
        try:
            despesas = c.fetchall()
        except:
            despesas = []
    
    if despesas:
        st.write("### 📋 Despesas Recentes")
        despesas_df = pd.DataFrame(despesas, columns=colunas_df)
        st.dataframe(despesas_df, use_container_width=True)
        
        # Resumo por categoria - verificar se categoria existe
        st.write("### 📊 Resumo por Categoria")
        try:
            if 'categoria' in colunas_despesas and 'fundo_id' in colunas_despesas:
                c.execute("SELECT categoria, SUM(valor) FROM despesas WHERE fundo_id = ? GROUP BY categoria ORDER BY SUM(valor) DESC", (fundo_id,))
            elif 'fundo_id' in colunas_despesas:
                # Sem categoria, agrupar tudo como "Geral"
                c.execute("SELECT 'Geral' as categoria, SUM(valor) FROM despesas WHERE fundo_id = ?", (fundo_id,))
            elif 'categoria' in colunas_despesas:
                c.execute("SELECT categoria, SUM(valor) FROM despesas GROUP BY categoria ORDER BY SUM(valor) DESC")
            else:
                # Sem categoria nem fundo_id
                c.execute("SELECT 'Geral' as categoria, SUM(valor) FROM despesas")
            
            resumo_categorias = c.fetchall()
        except Exception as e:
            print(f"Erro ao consultar resumo de categorias: {e}")
            resumo_categorias = []
        
        if resumo_categorias:
            resumo_df = pd.DataFrame(resumo_categorias, columns=['Categoria', 'Total'])
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.dataframe(resumo_df, use_container_width=True)
            
            with col2:
                fig = px.pie(resumo_df, values='Total', names='Categoria', 
                           title=f'Despesas por Categoria - {fundo_info[1]}')
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📝 Nenhuma despesa registrada para este fundo")
    
    st.divider()
    
    # Registrar nova despesa
    st.write("### ➕ Registrar Nova Despesa")
    
    categorias_despesas = ["Administrativa", "Operacional", "Financeira", "Marketing", "Tecnologia", "Geral"]
    
    with st.form("despesa_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            data_despesa = st.date_input("📅 Data", value=datetime.now().date())
            valor_despesa = st.number_input("💰 Valor (USD)", min_value=0.01, step=0.01)
        
        with col2:
            categoria_despesa = st.selectbox("📂 Categoria", categorias_despesas)
            descricao_despesa = st.text_input("📝 Descrição")
        
        submitted = st.form_submit_button("💼 Registrar Despesa", type="primary")
        
        if submitted:
            if valor_despesa > 0 and descricao_despesa:
                try:
                    c.execute("""INSERT INTO despesas (fundo_id, data, descricao, valor, categoria)
                                VALUES (?, ?, ?, ?, ?)""",
                             (fundo_id, data_despesa, descricao_despesa, valor_despesa, categoria_despesa))
                    conn.commit()
                    
                    st.success(f"✅ Despesa registrada com sucesso!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao registrar despesa: {str(e)}")
            else:
                st.error("❌ Preencha todos os campos obrigatórios")

def show_octav_integration_section(fundo_id):
    """Seção de integração Octav para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    st.subheader(f"🔄 Integração Octav.fi - {fundo_info[1]}")
    
    # Criar abas para organizar melhor
    tab1, tab2, tab3 = st.tabs(["🔄 Atualização AUM", "💾 Backup", "⚙️ Configurações"])
    
    with tab1:
        # Verificar configuração de automação
        c = conn.cursor()
        c.execute("SELECT atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas FROM configuracoes_automacao WHERE fundo_id = ?", (fundo_id,))
        config_auto = c.fetchone()
        
        if not config_auto:
            # Criar configuração padrão se não existir
            c.execute("INSERT INTO configuracoes_automacao (fundo_id, atualizacao_automatica_ativa, ultima_atualizacao_automatica, intervalo_horas) VALUES (?, 1, '', 24)", (fundo_id,))
            conn.commit()
            config_auto = (1, '', 24)
        
        ativa, ultima_atualizacao, intervalo_horas = config_auto
        
        # Seção de configurações de automação
        st.write("### ⚙️ Configurações de Automação")
        
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            nova_ativa = st.toggle(f"🔄 Atualização Automática Diária - {fundo_info[1]}", value=bool(ativa))
            
            if nova_ativa != bool(ativa):
                c.execute("UPDATE configuracoes_automacao SET atualizacao_automatica_ativa = ? WHERE fundo_id = ?", (nova_ativa, fundo_id))
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
            api_token, wallet_address = get_octav_config(fundo_id)
            
            st.info("**Atualização do AUM via API Octav.fi**")
            st.write(f"**Wallet monitorada:** `{wallet_address}`")
            
            # Mostrar informações da última atualização
            updater = get_octav_updater(fundo_id)
            # Note: Precisa modificar FundAUMUpdater para aceitar fundo_id
            
            c.execute("SELECT timestamp, valor, status FROM logs_aum WHERE fundo_id = ? ORDER BY timestamp DESC LIMIT 1", (fundo_id,))
            last_update = c.fetchone()
            
            if last_update:
                st.write("**Última atualização:**")
                status_color = "🟢" if last_update[2] == 'SUCESSO' else "🔴"
                st.write(f"{status_color} {last_update[0]} - ${last_update[1]:,.2f} USD")
            else:
                st.write("⚪ Nenhuma atualização realizada ainda")
        
        with col2:
            st.write("**Ações:**")
            
            # Botão para atualização manual
            if st.button(f"🔄 Atualizar AUM Agora - {fundo_info[1]}", type="primary"):
                with st.spinner("Buscando dados da Octav.fi..."):
                    try:
                        api_token, wallet_address = get_octav_config(fundo_id)
                        octav_api = OctavAPI(api_token, wallet_address)
                        updater = FundAUMUpdater('fundo_usdt.db', octav_api)
                        
                        success, message, data = updater.update_aum_from_octav(fundo_id)
                        
                        if success:
                            st.success(message)
                            if data:
                                st.json(data)
                            # Atualizar timestamp da última atualização automática se automação estiver ativa
                            if nova_ativa:
                                c.execute("UPDATE configuracoes_automacao SET ultima_atualizacao_automatica = ? WHERE fundo_id = ?", 
                                         (datetime.now().isoformat(), fundo_id))
                                conn.commit()
                            st.rerun()
                        else:
                            st.error(message)
                    except Exception as e:
                        st.error(f"❌ Erro: {str(e)}")
            
            # Botão para verificar se precisa atualizar
            if st.button(f"📊 Verificar Status - {fundo_info[1]}"):
                aum_hoje = verificar_aum_atualizado(fundo_id)
                
                if aum_hoje:
                    st.success("✅ AUM já foi atualizado hoje")
                else:
                    st.warning("⚠️ AUM precisa ser atualizado hoje")
    
    with tab2:
        show_backup_section()
    
    with tab3:
        show_octav_config_section(fundo_id)

def show_backup_section():
    """Seção de backup (global)"""
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
            nome_arquivo = f"multifundos_atual_{timestamp_atual}.db"
            
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

def show_octav_config_section(fundo_id):
    """Seção de configurações Octav para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    st.write(f"### ⚙️ Configurações da API Octav.fi - {fundo_info[1]}")
    
    # Obter configurações atuais
    api_token, wallet_address = get_octav_config(fundo_id)
    
    with st.form(f"config_octav_form_{fundo_id}"):
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
                    update_octav_config(fundo_id, novo_token, nova_wallet)
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
        WHERE fundo_id = ?
        ORDER BY timestamp DESC 
        LIMIT 10
    """, (fundo_id,))
    logs = c.fetchall()
    
    if logs:
        logs_df = pd.DataFrame(logs, columns=[
            'Timestamp', 'Tipo', 'Fonte', 'Valor', 'Status', 'Detalhes', 'Erro'
        ])
        st.dataframe(logs_df, use_container_width=True)
    else:
        st.info("Nenhum log encontrado para este fundo")

def show_settings_section(fundo_id):
    """Seção de configurações para um fundo específico"""
    fundo_info = get_fundo_by_id(fundo_id)
    
    st.subheader(f"⚙️ Configurações - {fundo_info[1]}")
    
    # Configurações do fundo - usar consulta compatível
    c = conn.cursor()
    try:
        # Verificar estrutura da tabela configuracoes_fundo
        c.execute("PRAGMA table_info(configuracoes_fundo)")
        colunas_config = [row[1] for row in c.fetchall()]
        
        # Construir consulta baseada nas colunas disponíveis
        colunas_desejadas = ['nome', 'data_inicio', 'valor_cota_inicial', 'aum_inicial', 'taxa_administracao', 'taxa_performance']
        colunas_disponiveis = [col for col in colunas_desejadas if col in colunas_config]
        
        if colunas_disponiveis:
            if 'fundo_id' in colunas_config:
                query = f"SELECT {', '.join(colunas_disponiveis)} FROM configuracoes_fundo WHERE fundo_id = ?"
                c.execute(query, (fundo_id,))
            else:
                query = f"SELECT {', '.join(colunas_disponiveis)} FROM configuracoes_fundo LIMIT 1"
                c.execute(query)
            
            config_result = c.fetchone()
            
            # Preencher valores padrão para colunas faltantes
            config_dict = {}
            for i, col in enumerate(colunas_disponiveis):
                config_dict[col] = config_result[i] if config_result else None
            
            # Valores padrão para colunas faltantes
            nome_atual = config_dict.get('nome', 'Fundo USDT')
            data_inicio = config_dict.get('data_inicio', '2024-01-01')
            valor_cota_inicial = config_dict.get('valor_cota_inicial', 1.0)
            aum_inicial = config_dict.get('aum_inicial', 50000.0)
            taxa_admin = config_dict.get('taxa_administracao', 2.0)
            taxa_perf = config_dict.get('taxa_performance', 20.0)
            
            config = (nome_atual, data_inicio, valor_cota_inicial, aum_inicial, taxa_admin, taxa_perf)
        else:
            # Se nenhuma coluna está disponível, usar valores padrão
            config = ('Fundo USDT', '2024-01-01', 1.0, 50000.0, 2.0, 20.0)
            nome_atual, data_inicio, valor_cota_inicial, aum_inicial, taxa_admin, taxa_perf = config
    
    except Exception as e:
        print(f"Erro ao carregar configurações: {e}")
        # Valores padrão em caso de erro
        config = ('Fundo USDT', '2024-01-01', 1.0, 50000.0, 2.0, 20.0)
        nome_atual, data_inicio, valor_cota_inicial, aum_inicial, taxa_admin, taxa_perf = config
    
    if config:
        nome_atual, data_inicio, valor_cota_inicial, aum_inicial, taxa_admin, taxa_perf = config
        
        st.write("### 🏦 Configurações do Fundo")
        
        with st.form(f"config_fundo_form_{fundo_id}"):
            col1, col2 = st.columns(2)
            
            with col1:
                novo_nome = st.text_input("📝 Nome do Fundo", value=nome_atual)
                # Tratar data_inicio que pode ser None
                try:
                    data_default = datetime.strptime(data_inicio, '%Y-%m-%d').date() if data_inicio else datetime(2024, 1, 1).date()
                except (ValueError, TypeError):
                    data_default = datetime(2024, 1, 1).date()
                nova_data_inicio = st.date_input("📅 Data de Início", value=data_default)
                novo_valor_cota = st.number_input("💎 Valor Inicial da Cota", value=float(valor_cota_inicial or 1.0), step=0.0001)
            
            with col2:
                novo_aum_inicial = st.number_input("💰 AUM Inicial", value=float(aum_inicial or 50000.0), step=0.01)
                nova_taxa_admin = st.number_input("📊 Taxa de Administração (%)", value=float(taxa_admin or 0), step=0.01)
                nova_taxa_perf = st.number_input("🎯 Taxa de Performance (%)", value=float(taxa_perf or 0), step=0.01)
            
            submitted = st.form_submit_button("💾 Salvar Configurações", type="primary")
            
            if submitted:
                try:
                    c.execute("""UPDATE configuracoes_fundo 
                                SET nome = ?, data_inicio = ?, valor_cota_inicial = ?, 
                                    aum_inicial = ?, taxa_administracao = ?, taxa_performance = ?
                                WHERE fundo_id = ?""",
                             (novo_nome, nova_data_inicio, novo_valor_cota, novo_aum_inicial, 
                              nova_taxa_admin, nova_taxa_perf, fundo_id))
                    
                    # Atualizar também na tabela fundos
                    c.execute("UPDATE fundos SET nome = ?, data_inicio = ?, valor_cota_inicial = ? WHERE id = ?",
                             (novo_nome, nova_data_inicio, novo_valor_cota, fundo_id))
                    
                    conn.commit()
                    st.success("✅ Configurações atualizadas com sucesso!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao atualizar configurações: {str(e)}")
    
    st.divider()
    
    # Informações do sistema
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 📊 Estatísticas do Fundo")
        
        # Total de clientes
        c.execute("SELECT COUNT(DISTINCT cliente_id) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
        total_clientes = c.fetchone()[0]
        
        # Total de movimentações
        c.execute("SELECT COUNT(*) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
        total_movimentacoes = c.fetchone()[0]
        
        # Total investido
        c.execute("SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN valor ELSE -valor END), 0) FROM movimentacoes WHERE fundo_id = ?", (fundo_id,))
        total_investido = c.fetchone()[0]
        
        # AUM atual - usar consulta compatível
        aum_result = consulta_compativel(c, 'aum_diario', 'valor', fundo_id, 'data DESC', 1)
        aum_atual = aum_result[0][0] if aum_result else 0
        
        st.metric("👥 Total de Clientes", total_clientes)
        st.metric("📈 Total de Movimentações", total_movimentacoes)
        st.metric("💼 Total Investido", f"${total_investido:,.2f}")
        st.metric("💰 AUM Atual", f"${aum_atual:,.2f}")
    
    with col2:
        st.write("### 🔐 Configurações de API")
        
        st.info("**Octav.fi API**")
        api_token, wallet_address = get_octav_config(fundo_id)
        st.code(f"Token: {api_token[:20]}...")
        st.code(f"Wallet: {wallet_address}")

def client_dashboard(cliente_id, cliente_nome):
    """Dashboard do cliente com visão multi-fundos"""
    st.title(f"👤 Área do Cliente - {cliente_nome}")
    
    # Sidebar com informações do cliente
    with st.sidebar:
        st.success(f"👤 Cliente")
        st.info(f"📧 {st.session_state.user_email}")
        st.info(f"👋 Bem-vindo, {cliente_nome}!")
        
        if st.button("🚪 Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Obter investimentos do cliente em todos os fundos
    investimentos = get_cliente_investimentos(cliente_id)
    
    if not investimentos:
        st.info("📝 Você ainda não possui investimentos em nenhum fundo.")
        st.write("Entre em contato com o administrador para realizar seu primeiro investimento.")
        return
    
    # Dashboard geral
    st.subheader("📊 Resumo Geral dos Investimentos")
    
    # Métricas gerais
    total_investido_geral = sum([inv[3] for inv in investimentos])
    total_cotas_geral = sum([inv[2] for inv in investimentos])
    
    # Calcular valor atual total
    valor_atual_total = 0
    for inv in investimentos:
        fundo_id, fundo_nome, total_cotas, total_investido = inv
        valor_cota_atual = get_valor_cota_atual(fundo_id)
        valor_atual_total += total_cotas * valor_cota_atual
    
    rentabilidade_geral = ((valor_atual_total - total_investido_geral) / total_investido_geral * 100) if total_investido_geral > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("💼 Total Investido", f"${total_investido_geral:,.2f}")
    
    with col2:
        st.metric("💰 Valor Atual", f"${valor_atual_total:,.2f}")
    
    with col3:
        delta_color = "normal" if rentabilidade_geral >= 0 else "inverse"
        st.metric("📈 Rentabilidade", f"{rentabilidade_geral:.2f}%", 
                 delta=f"${valor_atual_total - total_investido_geral:,.2f}", delta_color=delta_color)
    
    with col4:
        st.metric("🏦 Fundos Investidos", len(investimentos))
    
    st.divider()
    
    # Detalhes por fundo
    st.subheader("🏦 Detalhes por Fundo")
    
    # Criar abas para cada fundo
    if len(investimentos) == 1:
        # Se apenas um fundo, mostrar diretamente
        show_client_fund_details(cliente_id, investimentos[0])
    else:
        # Se múltiplos fundos, criar abas
        fund_tabs = st.tabs([f"🏦 {inv[1]}" for inv in investimentos])
        
        for i, (tab, investimento) in enumerate(zip(fund_tabs, investimentos)):
            with tab:
                show_client_fund_details(cliente_id, investimento)

def show_client_fund_details(cliente_id, investimento):
    """Mostra detalhes de um fundo específico para o cliente"""
    fundo_id, fundo_nome, total_cotas, total_investido = investimento
    
    # Informações do fundo
    fundo_info = get_fundo_by_id(fundo_id)
    valor_cota_atual = get_valor_cota_atual(fundo_id)
    valor_atual = total_cotas * valor_cota_atual
    rentabilidade = ((valor_atual - total_investido) / total_investido * 100) if total_investido > 0 else 0
    
    # Métricas do fundo
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("💼 Investido", f"${total_investido:,.2f}")
    
    with col2:
        st.metric("📊 Cotas", f"{total_cotas:.6f}")
    
    with col3:
        st.metric("💎 Valor da Cota", f"${valor_cota_atual:.4f}")
    
    with col4:
        delta_color = "normal" if rentabilidade >= 0 else "inverse"
        st.metric("💰 Valor Atual", f"${valor_atual:,.2f}", 
                 delta=f"{rentabilidade:.2f}%", delta_color=delta_color)
    
    # Histórico de movimentações do cliente neste fundo
    st.write("### 📋 Histórico de Movimentações")
    
    c = conn.cursor()
    c.execute("""SELECT tipo, valor, cotas, valor_cota, data, observacoes
                 FROM movimentacoes 
                 WHERE fundo_id = ? AND cliente_id = ?
                 ORDER BY data DESC, id DESC""", (fundo_id, cliente_id))
    movimentacoes_cliente = c.fetchall()
    
    if movimentacoes_cliente:
        movimentacoes_df = pd.DataFrame(movimentacoes_cliente, columns=[
            'Tipo', 'Valor (USD)', 'Cotas', 'Valor da Cota', 'Data', 'Observações'
        ])
        st.dataframe(movimentacoes_df, use_container_width=True)
    else:
        st.info("📝 Nenhuma movimentação encontrada")
    
    # Gráfico de evolução do investimento
    if movimentacoes_cliente:
        st.write("### 📈 Evolução do Investimento")
        
        # Calcular evolução acumulada
        evolucao_data = []
        cotas_acumuladas = 0
        valor_investido_acumulado = 0
        
        for mov in reversed(movimentacoes_cliente):  # Reverter para ordem cronológica
            tipo, valor, cotas, valor_cota, data, obs = mov
            
            if tipo == 'ENTRADA':
                cotas_acumuladas += cotas
                valor_investido_acumulado += valor
            else:
                cotas_acumuladas -= cotas
                valor_investido_acumulado -= valor
            
            evolucao_data.append({
                'Data': data,
                'Cotas_Acumuladas': cotas_acumuladas,
                'Valor_Investido': valor_investido_acumulado,
                'Valor_Cota': valor_cota
            })
        
        if evolucao_data:
            evolucao_df = pd.DataFrame(evolucao_data)
            evolucao_df['Data'] = pd.to_datetime(evolucao_df['Data'])
            evolucao_df['Valor_Posicao'] = evolucao_df['Cotas_Acumuladas'] * evolucao_df['Valor_Cota']
            
            fig = px.line(evolucao_df, x='Data', y=['Valor_Investido', 'Valor_Posicao'],
                         title=f'Evolução do Investimento - {fundo_nome}',
                         labels={'value': 'Valor (USD)', 'Data': 'Data'})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()

