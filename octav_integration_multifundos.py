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
            "Content-Type": "application/json"
        }
    
    def get_historical_portfolio(self, date=None):
        """
        Busca o valor histórico do portfólio para uma data específica
        
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
            logger.info(f"Buscando dados do portfólio para {date}")
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Dados obtidos com sucesso para {date}")
                return data
            else:
                logger.error(f"Erro na API: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de conexão com a API: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado: {str(e)}")
            return None
    
    def extract_networth(self, portfolio_data):
        """
        Extrai o valor líquido (networth) dos dados do portfólio
        
        Args:
            portfolio_data (dict): Dados retornados pela API
        
        Returns:
            float: Valor líquido do portfólio ou 0 em caso de erro
        """
        try:
            if not portfolio_data:
                return 0.0
            
            # A estrutura exata pode variar, mas geralmente está em data.networth ou similar
            if 'data' in portfolio_data:
                data = portfolio_data['data']
                
                # Tentar diferentes estruturas possíveis
                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    if 'networth' in item:
                        return float(item['networth'])
                    elif 'total_value' in item:
                        return float(item['total_value'])
                    elif 'portfolio_value' in item:
                        return float(item['portfolio_value'])
                
                elif isinstance(data, dict):
                    if 'networth' in data:
                        return float(data['networth'])
                    elif 'total_value' in data:
                        return float(data['total_value'])
                    elif 'portfolio_value' in data:
                        return float(data['portfolio_value'])
            
            # Se não encontrou na estrutura esperada, tentar no nível raiz
            if 'networth' in portfolio_data:
                return float(portfolio_data['networth'])
            elif 'total_value' in portfolio_data:
                return float(portfolio_data['total_value'])
            
            logger.warning("Estrutura de dados não reconhecida")
            logger.debug(f"Dados recebidos: {json.dumps(portfolio_data, indent=2)}")
            return 0.0
            
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Erro ao extrair networth: {str(e)}")
            return 0.0

class FundAUMUpdater:
    """Classe para atualizar o AUM de fundos específicos com dados da Octav"""
    
    def __init__(self, db_path, octav_api):
        self.db_path = db_path
        self.octav_api = octav_api
    
    def get_db_connection(self):
        """Cria conexão com o banco de dados"""
        return sqlite3.connect(self.db_path)
    
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
    
    def update_aum_from_octav(self, fundo_id, date=None, manual_expenses=0):
        """
        Atualiza o AUM de um fundo específico com dados da API Octav
        
        Args:
            fundo_id (int): ID do fundo a ser atualizado
            date (str): Data no formato YYYY-MM-DD. Se None, usa data atual.
            manual_expenses (float): Despesas manuais a serem consideradas
        
        Returns:
            tuple: (sucesso, mensagem, dados)
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            # Buscar dados do portfólio na Octav
            portfolio_data = self.octav_api.get_historical_portfolio(date)
            
            if not portfolio_data:
                self._log_aum_operation(fundo_id, 'ERRO', 'octav', None, 'ERRO', 
                                       "Erro ao obter dados da API Octav", "Falha na conexão com API")
                return False, "Erro ao obter dados da API Octav", None
            
            # Extrair valor líquido
            networth = self.octav_api.extract_networth(portfolio_data)
            
            if networth <= 0:
                self._log_aum_operation(fundo_id, 'ERRO', 'octav', networth, 'ERRO', 
                                       "Valor do portfólio inválido", "Networth <= 0")
                return False, "Valor do portfólio inválido ou zero", None
            
            # Obter despesas do fundo
            fund_expenses = self.get_fund_expenses(fundo_id, date) + manual_expenses
            
            # Calcular novo valor da cota
            new_quota_value = self.calculate_new_quota_value(fundo_id, networth, fund_expenses)
            
            # Atualizar no banco de dados
            conn = self.get_db_connection()
            c = conn.cursor()
            
            # Inserir/atualizar AUM diário
            c.execute("""INSERT OR REPLACE INTO aum_diario 
                        (fundo_id, data, valor, valor_cota, fonte) 
                        VALUES (?, ?, ?, ?, 'octav')""", 
                     (fundo_id, date, networth, new_quota_value))
            
            conn.commit()
            
            # Log da operação bem-sucedida
            self._log_aum_operation(fundo_id, 'ATUALIZACAO', 'octav', networth, 'SUCESSO', 
                                   f"AUM atualizado via Octav API: ${networth:,.2f} | Valor da cota: ${new_quota_value:.6f}")
            
            # Preparar dados de retorno
            return_data = {
                'date': date,
                'aum_value': networth,
                'quota_value': new_quota_value,
                'expenses': fund_expenses,
                'wallet_address': self.octav_api.wallet_address,
                'portfolio_data': portfolio_data
            }
            
            return True, f"AUM atualizado com sucesso: ${networth:,.2f} USD | Valor da cota: ${new_quota_value:.6f}", return_data
            
        except Exception as e:
            error_msg = f"Erro inesperado ao atualizar AUM do fundo {fundo_id}: {str(e)}"
            logger.error(error_msg)
            self._log_aum_operation(fundo_id, 'ERRO', 'octav', None, 'ERRO', 
                                   "Erro inesperado", str(e))
            return False, error_msg, None
        finally:
            if 'conn' in locals():
                conn.close()
    
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
            
            c.execute("""INSERT INTO logs_aum 
                        (fundo_id, timestamp, tipo, fonte, valor, status, detalhes, erro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                     (fundo_id, datetime.now().isoformat(), tipo, fonte, valor, status, detalhes, erro))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Erro ao registrar log: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_latest_aum(self, fundo_id):
        """
        Obtém o último AUM registrado para um fundo
        
        Args:
            fundo_id (int): ID do fundo
        
        Returns:
            tuple: (data, valor, valor_cota) ou None se não encontrado
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute("SELECT data, valor, valor_cota FROM aum_diario WHERE fundo_id = ? ORDER BY data DESC LIMIT 1", 
                     (fundo_id,))
            result = c.fetchone()
            return result
        except Exception as e:
            logger.error(f"Erro ao obter último AUM do fundo {fundo_id}: {str(e)}")
            return None
        finally:
            conn.close()
    
    def get_aum_history(self, fundo_id, days=30):
        """
        Obtém histórico de AUM de um fundo
        
        Args:
            fundo_id (int): ID do fundo
            days (int): Número de dias para buscar
        
        Returns:
            list: Lista de tuplas (data, valor, valor_cota)
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            c.execute("""SELECT data, valor, valor_cota FROM aum_diario 
                        WHERE fundo_id = ? AND data >= ? 
                        ORDER BY data ASC""", 
                     (fundo_id, start_date))
            return c.fetchall()
        except Exception as e:
            logger.error(f"Erro ao obter histórico de AUM do fundo {fundo_id}: {str(e)}")
            return []
        finally:
            conn.close()

# Função de teste/exemplo
def test_octav_integration(api_token, wallet_address, fundo_id=1):
    """
    Função de teste para a integração Octav
    
    Args:
        api_token (str): Token da API Octav
        wallet_address (str): Endereço da wallet
        fundo_id (int): ID do fundo para testar
    """
    print("=== Teste de Integração Octav.fi ===")
    
    # Inicializar API
    octav_api = OctavAPI(api_token, wallet_address)
    updater = FundAUMUpdater('fundo_usdt.db', octav_api)
    
    # Testar busca de dados
    print("1. Testando busca de dados do portfólio...")
    portfolio_data = octav_api.get_historical_portfolio()
    
    if portfolio_data:
        print("✅ Dados obtidos com sucesso")
        
        # Extrair networth
        networth = octav_api.extract_networth(portfolio_data)
        print(f"💰 Valor do portfólio: ${networth:,.2f} USD")
        
        # Testar atualização do AUM
        print(f"2. Testando atualização do AUM para fundo {fundo_id}...")
        success, message, data = updater.update_aum_from_octav(fundo_id)
        
        if success:
            print("✅ AUM atualizado com sucesso")
            print(f"📊 {message}")
            if data:
                print(f"📈 Valor da cota: ${data['quota_value']:.6f}")
        else:
            print("❌ Erro na atualização do AUM")
            print(f"🔴 {message}")
    else:
        print("❌ Erro ao obter dados do portfólio")
    
    print("=== Fim do Teste ===")

if __name__ == "__main__":
    # Exemplo de uso
    # Substitua pelos seus valores reais
    API_TOKEN = "seu_token_aqui"
    WALLET_ADDRESS = "0x..."
    
    # test_octav_integration(API_TOKEN, WALLET_ADDRESS, fundo_id=1)
    pass

