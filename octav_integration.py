import requests
import sqlite3
from datetime import datetime, timedelta
import json
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OctavAPI:
    """Classe para integração com a API da Octav.fi"""
    
    def __init__(self, api_token, wallet_address):
        self.base_url = "https://api.octav.fi"
        self.api_token = api_token
        self.wallet_address = wallet_address
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def get_current_portfolio(self):
        """
        Busca o valor atual do portfólio (dados em tempo real)
        
        Returns:
            dict: Dados do portfólio ou None em caso de erro
        """
        url = f"{self.base_url}/v1/portfolio"
        params = {
            "addresses": self.wallet_address
        }
        
        try:
            logger.info(f"Buscando dados atuais do portfólio para carteira {self.wallet_address}")
            logger.info(f"URL: {url}")
            logger.info(f"Params: {params}")
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            logger.info(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Dados obtidos com sucesso")
                logger.debug(f"Resposta completa: {json.dumps(data, indent=2)}")
                return data
            else:
                logger.error(f"❌ Erro na API: {response.status_code}")
                logger.error(f"Resposta: {response.text[:500]}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão com a API: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ Erro inesperado: {str(e)}")
            return None
    
    def get_historical_portfolio(self, date=None):
        """
        Busca o valor histórico do portfólio para uma data específica
        NOTA: Este endpoint pode não ter dados históricos disponíveis.
        Use get_current_portfolio() para dados atuais.
        
        Args:
            date (str): Data no formato YYYY-MM-DD. Se None, usa a data atual.
        
        Returns:
            dict: Dados do portfólio ou None em caso de erro
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        url = f"{self.base_url}/v1/historical"
        params = {
            "addresses": self.wallet_address,
            "date": date
        }
        
        try:
            logger.info(f"Buscando dados históricos do portfólio para {date}")
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Dados históricos obtidos para {date}")
                return data
            else:
                logger.warning(f"Dados históricos não disponíveis para {date} (Status: {response.status_code})")
                logger.info("Tentando obter dados atuais como fallback...")
                return self.get_current_portfolio()
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de conexão ao buscar dados históricos: {str(e)}")
            logger.info("Tentando obter dados atuais como fallback...")
            return self.get_current_portfolio()
        except Exception as e:
            logger.error(f"Erro inesperado ao buscar dados históricos: {str(e)}")
            return None
    
    def extract_networth(self, portfolio_data):
        """
        Extrai o valor líquido (networth) dos dados do portfólio
        
        Args:
            portfolio_data (dict or list): Dados retornados pela API
        
        Returns:
            float: Valor líquido do portfólio ou 0 em caso de erro
        """
        try:
            if not portfolio_data:
                logger.warning("Portfolio data is None or empty")
                return 0.0
            
            logger.info("Extraindo networth dos dados do portfólio...")
            
            # A API Octav.fi retorna uma LISTA de carteiras
            if isinstance(portfolio_data, list) and len(portfolio_data) > 0:
                wallet_data = portfolio_data[0]  # Primeiro item da lista
                if 'networth' in wallet_data:
                    networth = float(wallet_data['networth'])
                    logger.info(f"✅ Networth encontrado na lista: ${networth:,.2f} USD")
                    return networth
            
            # Estrutura alternativa: data.networth (para compatibilidade)
            if isinstance(portfolio_data, dict):
                if 'data' in portfolio_data:
                    data = portfolio_data['data']
                    
                    # Se data é uma lista
                    if isinstance(data, list) and len(data) > 0:
                        item = data[0]
                        if 'networth' in item:
                            networth = float(item['networth'])
                            logger.info(f"✅ Networth encontrado (data[0]): ${networth:,.2f} USD")
                            return networth
                    
                    # Se data é um dict
                    elif isinstance(data, dict) and 'networth' in data:
                        networth = float(data['networth'])
                        logger.info(f"✅ Networth encontrado (data): ${networth:,.2f} USD")
                        return networth
                
                # Tentar no nível raiz do dict
                if 'networth' in portfolio_data:
                    networth = float(portfolio_data['networth'])
                    logger.info(f"✅ Networth encontrado (raiz): ${networth:,.2f} USD")
                    return networth
                
                # Tentar outros campos comuns
                value_fields = ['total_value', 'portfolio_value', 'value', 'balance']
                for field in value_fields:
                    if field in portfolio_data:
                        networth = float(portfolio_data[field])
                        logger.info(f"✅ Valor encontrado em '{field}': ${networth:,.2f} USD")
                        return networth
            
            logger.warning("⚠️ Estrutura de dados não reconhecida")
            logger.debug(f"Tipo: {type(portfolio_data)}")
            if isinstance(portfolio_data, list):
                logger.debug(f"Lista com {len(portfolio_data)} itens")
                if len(portfolio_data) > 0:
                    logger.debug(f"Primeiro item: {str(portfolio_data[0])[:200]}")
            else:
                logger.debug(f"Estrutura: {json.dumps(portfolio_data, indent=2)[:500]}")
            return 0.0
            
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"❌ Erro ao extrair networth: {str(e)}")
            return 0.0

class FundAUMUpdater:
    """Classe para atualizar o AUM de fundos específicos com dados da Octav"""
    
    def __init__(self, db_path, octav_api):
        self.db_path = db_path
        self.octav_api = octav_api
    
    def get_db_connection(self):
        """Cria conexão com o banco de dados"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def calculate_new_quota_value(self, fundo_id, total_aum, total_expenses=0):
        """
        Calcula o novo valor da cota baseado no AUM total para um fundo específico
        
        Args:
            fundo_id (int): ID do fundo
            total_aum (float): Valor total do AUM
            total_expenses (float): Despesas totais
        
        Returns:
            float: Novo valor da cota
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            # Buscar total de cotas em circulação para este fundo
            c.execute("""SELECT COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN cotas ELSE -cotas END), 0) 
                        FROM movimentacoes WHERE fundo_id = ?""", (fundo_id,))
            result = c.fetchone()
            total_cotas = result[0] if result[0] else 0
            
            # Se não há cotas, usar valor inicial do fundo
            if total_cotas <= 0:
                c.execute("SELECT valor_cota_inicial FROM fundos WHERE id = ?", (fundo_id,))
                result = c.fetchone()
                return result[0] if result else 1.0
            
            # Calcular valor da cota: (AUM - Despesas) / Total de Cotas
            net_aum = total_aum - total_expenses
            quota_value = net_aum / total_cotas if total_cotas > 0 else 1.0
            
            return max(quota_value, 0.0001)  # Valor mínimo para evitar cotas zeradas
            
        except Exception as e:
            logger.error(f"Erro ao calcular valor da cota para fundo {fundo_id}: {str(e)}")
            return 1.0
        finally:
            conn.close()
    
    def get_fund_expenses(self, fundo_id, date=None):
        """
        Obtém o total de despesas de um fundo até uma data específica
        
        Args:
            fundo_id (int): ID do fundo
            date (str): Data limite no formato YYYY-MM-DD
        
        Returns:
            float: Total de despesas
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute("SELECT COALESCE(SUM(valor), 0) FROM despesas WHERE fundo_id = ? AND data <= ?", 
                     (fundo_id, date))
            result = c.fetchone()
            return result[0] if result else 0.0
        except Exception as e:
            logger.error(f"Erro ao obter despesas do fundo {fundo_id}: {str(e)}")
            return 0.0
        finally:
            conn.close()
    
    def update_aum_from_octav(self, fundo_id, date=None, manual_expenses=0, use_current=True):
        """
        Atualiza o AUM de um fundo específico com dados da API Octav
        
        Args:
            fundo_id (int): ID do fundo a ser atualizado
            date (str): Data no formato YYYY-MM-DD. Se None, usa data atual.
            manual_expenses (float): Despesas manuais a serem consideradas
            use_current (bool): Se True, usa dados atuais. Se False, tenta dados históricos.
        
        Returns:
            tuple: (sucesso, mensagem, dados)
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            logger.info(f"=" * 80)
            logger.info(f"INICIANDO ATUALIZAÇÃO DE AUM - Fundo ID: {fundo_id}")
            logger.info(f"Data: {date} | Use Current: {use_current}")
            logger.info(f"=" * 80)
            
            # Buscar dados do portfólio na Octav
            if use_current:
                portfolio_data = self.octav_api.get_current_portfolio()
            else:
                portfolio_data = self.octav_api.get_historical_portfolio(date)
            
            if not portfolio_data:
                error_msg = "Erro ao obter dados da API Octav - Sem resposta"
                logger.error(f"❌ {error_msg}")
                self._log_aum_operation(fundo_id, 'ERRO', 'octav', None, 'ERRO', 
                                       error_msg, "API retornou None")
                return False, error_msg, None
            
            # Extrair valor líquido
            networth = self.octav_api.extract_networth(portfolio_data)
            
            if networth <= 0:
                error_msg = f"Valor do portfólio inválido ou zero: ${networth}"
                logger.error(f"❌ {error_msg}")
                logger.info("💡 Dica: Verifique se a carteira possui saldo ou se o token da API está correto")
                self._log_aum_operation(fundo_id, 'ERRO', 'octav', networth, 'ERRO', 
                                       error_msg, "Networth <= 0")
                return False, error_msg, None
            
            logger.info(f"✅ Networth obtido: ${networth:,.2f} USD")
            
            # Obter despesas do fundo
            fund_expenses = self.get_fund_expenses(fundo_id, date) + manual_expenses
            logger.info(f"📊 Despesas do fundo: ${fund_expenses:,.2f} USD")
            
            # Calcular novo valor da cota
            new_quota_value = self.calculate_new_quota_value(fundo_id, networth, fund_expenses)
            logger.info(f"💰 Novo valor da cota: ${new_quota_value:.6f}")
            
            # Atualizar no banco de dados
            conn = self.get_db_connection()
            c = conn.cursor()
            
            # Inserir/atualizar AUM diário
            # Nota: tabela aum_diario não tem coluna 'fundo_id', apenas 'data', 'valor_total', 'valor_cota', 'despesas'
            c.execute("""INSERT OR REPLACE INTO aum_diario 
                        (data, valor_total, valor_cota, despesas) 
                        VALUES (?, ?, ?, ?)""", 
                     (date, networth, new_quota_value, fund_expenses))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ AUM atualizado no banco de dados com sucesso!")
            
            # Log da operação bem-sucedida
            success_msg = f"AUM atualizado via Octav API: ${networth:,.2f} | Valor da cota: ${new_quota_value:.6f}"
            self._log_aum_operation(fundo_id, 'ATUALIZACAO', 'octav', networth, 'SUCESSO', success_msg)
            
            # Preparar dados de retorno
            return_data = {
                'date': date,
                'aum_value': networth,
                'quota_value': new_quota_value,
                'expenses': fund_expenses,
                'wallet_address': self.octav_api.wallet_address,
                'portfolio_data': portfolio_data
            }
            
            logger.info(f"=" * 80)
            logger.info(f"ATUALIZAÇÃO CONCLUÍDA COM SUCESSO")
            logger.info(f"=" * 80)
            
            return True, f"AUM atualizado com sucesso: ${networth:,.2f} USD | Valor da cota: ${new_quota_value:.6f}", return_data
            
        except Exception as e:
            error_msg = f"Erro inesperado ao atualizar AUM do fundo {fundo_id}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            logger.exception("Detalhes do erro:")
            self._log_aum_operation(fundo_id, 'ERRO', 'octav', None, 'ERRO', 
                                   "Erro inesperado", str(e))
            return False, error_msg, None
    
    def _log_aum_operation(self, fundo_id, tipo, fonte, valor, status, detalhes, erro=None):
        """
        Registra log da operação de AUM
        
        Args:
            fundo_id (int): ID do fundo
            tipo (str): Tipo da operação
            fonte (str): Fonte dos dados
            valor (float): Valor do AUM
            status (str): Status da operação
            detalhes (str): Detalhes da operação
            erro (str): Mensagem de erro, se houver
        """
        try:
            conn = self.get_db_connection()
            c = conn.cursor()
            
            # Verificar se a tabela existe
            c.execute("""SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='logs_aum'""")
            
            if not c.fetchone():
                # Criar tabela se não existir
                c.execute("""CREATE TABLE IF NOT EXISTS logs_aum (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fundo_id INTEGER,
                    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tipo TEXT,
                    fonte TEXT,
                    valor REAL,
                    status TEXT,
                    detalhes TEXT,
                    erro TEXT,
                    FOREIGN KEY (fundo_id) REFERENCES fundos(id)
                )""")
            
            c.execute("""INSERT INTO logs_aum 
                        (fundo_id, tipo, fonte, valor, status, detalhes, erro) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (fundo_id, tipo, fonte, valor, status, detalhes, erro))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Erro ao registrar log de AUM: {str(e)}")

def test_octav_connection(api_token, wallet_address):
    """
    Testa a conexão com a API Octav.fi
    
    Args:
        api_token (str): Token de autenticação da API
        wallet_address (str): Endereço da carteira
    
    Returns:
        tuple: (sucesso, mensagem, dados)
    """
    try:
        logger.info("Testando conexão com API Octav.fi...")
        
        octav = OctavAPI(api_token, wallet_address)
        portfolio_data = octav.get_current_portfolio()
        
        if not portfolio_data:
            return False, "Falha ao conectar com a API Octav.fi", None
        
        networth = octav.extract_networth(portfolio_data)
        
        if networth > 0:
            return True, f"Conexão bem-sucedida! Portfolio: ${networth:,.2f} USD", {
                'networth': networth,
                'wallet': wallet_address,
                'data': portfolio_data
            }
        else:
            return False, "Conexão estabelecida mas portfolio retornou valor zero", portfolio_data
    
    except Exception as e:
        return False, f"Erro ao testar conexão: {str(e)}", None

