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
            logger.error(f"Erro de conexão: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON: {str(e)}")
            return None
    
    def extract_networth(self, portfolio_data):
        """
        Extrai o valor líquido (networth) dos dados do portfólio
        
        Args:
            portfolio_data (dict): Dados retornados pela API
        
        Returns:
            float: Valor líquido em USD ou 0 se não encontrado
        """
        try:
            if portfolio_data and isinstance(portfolio_data, list) and len(portfolio_data) > 0:
                networth = portfolio_data[0].get('networth', '0')
                # Converter string para float
                return float(networth) if networth != 'N/A' else 0.0
            return 0.0
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Erro ao extrair networth: {str(e)}")
            return 0.0

class FundAUMUpdater:
    """Classe para atualizar o AUM do fundo com dados da Octav"""
    
    def __init__(self, db_path, octav_api):
        self.db_path = db_path
        self.octav_api = octav_api
    
    def get_db_connection(self):
        """Cria conexão com o banco de dados"""
        return sqlite3.connect(self.db_path)
    
    def calculate_new_quota_value(self, total_aum, total_expenses=0):
        """
        Calcula o novo valor da cota baseado no AUM total
        
        Args:
            total_aum (float): Valor total do AUM
            total_expenses (float): Despesas totais
        
        Returns:
            float: Novo valor da cota
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            # Buscar total de cotas em circulação (excluindo admin)
            c.execute("SELECT SUM(cotas) FROM clientes WHERE id > 1")
            result = c.fetchone()
            total_cotas = result[0] if result[0] else 1.0
            
            # Calcular valor da cota: (AUM - Despesas) / Total de Cotas
            net_aum = total_aum - total_expenses
            quota_value = net_aum / total_cotas if total_cotas > 0 else 1.0
            
            return max(quota_value, 0.0001)  # Valor mínimo para evitar cotas zeradas
            
        except Exception as e:
            logger.error(f"Erro ao calcular valor da cota: {str(e)}")
            return 1.0
        finally:
            conn.close()
    
    def update_aum_from_octav(self, date=None, manual_expenses=0):
        """
        Atualiza o AUM do fundo com dados da API Octav
        
        Args:
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
                return False, "Erro ao obter dados da API Octav", None
            
            # Extrair valor líquido
            networth = self.octav_api.extract_networth(portfolio_data)
            
            if networth <= 0:
                return False, "Valor do portfólio inválido ou zero", None
            
            # Calcular novo valor da cota
            quota_value = self.calculate_new_quota_value(networth, manual_expenses)
            
            # Atualizar banco de dados
            conn = self.get_db_connection()
            c = conn.cursor()
            
            # Inserir ou atualizar registro de AUM
            c.execute("""
                INSERT OR REPLACE INTO aum_diario (data, valor_total, valor_cota, despesas) 
                VALUES (?, ?, ?, ?)
            """, (date, networth, quota_value, manual_expenses))
            
            # Registrar log da atualização automática
            c.execute("""
                INSERT INTO logs_aum (timestamp, tipo, fonte, valor, status, detalhes) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                'ATUALIZACAO_AUTOMATICA',
                'OCTAV_API',
                networth,
                'SUCESSO',
                f"AUM atualizado automaticamente via Octav API. Valor da cota: {quota_value:.4f}"
            ))
            
            conn.commit()
            conn.close()
            
            result_data = {
                'date': date,
                'networth': networth,
                'quota_value': quota_value,
                'expenses': manual_expenses,
                'source': 'Octav API'
            }
            
            logger.info(f"AUM atualizado com sucesso: {networth} USD, Cota: {quota_value:.4f}")
            return True, f"AUM atualizado com sucesso! Valor: ${networth:,.2f} USD", result_data
            
        except Exception as e:
            logger.error(f"Erro ao atualizar AUM: {str(e)}")
            
            # Registrar erro no log
            try:
                conn = self.get_db_connection()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO logs_aum (timestamp, tipo, fonte, valor, status, detalhes, erro) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    'ATUALIZACAO_AUTOMATICA',
                    'OCTAV_API',
                    0,
                    'ERRO',
                    'Falha na atualização automática do AUM',
                    str(e)
                ))
                conn.commit()
                conn.close()
            except:
                pass
            
            return False, f"Erro ao atualizar AUM: {str(e)}", None
    
    def get_last_update_info(self):
        """
        Obtém informações da última atualização automática
        
        Returns:
            dict: Informações da última atualização ou None
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                SELECT timestamp, valor, status, detalhes 
                FROM logs_aum 
                WHERE fonte = 'OCTAV_API' AND tipo = 'ATUALIZACAO_AUTOMATICA'
                ORDER BY timestamp DESC 
                LIMIT 1
            """)
            
            result = c.fetchone()
            if result:
                return {
                    'timestamp': result[0],
                    'valor': result[1],
                    'status': result[2],
                    'detalhes': result[3]
                }
            return None
            
        except Exception as e:
            logger.error(f"Erro ao buscar última atualização: {str(e)}")
            return None
        finally:
            conn.close()
    
    def should_update_today(self):
        """
        Verifica se já foi feita atualização hoje
        
        Returns:
            bool: True se deve atualizar, False se já foi atualizado hoje
        """
        today = datetime.now().strftime('%Y-%m-%d')
        
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            # Verificar se já existe registro de AUM para hoje
            c.execute("SELECT COUNT(*) FROM aum_diario WHERE data = ?", (today,))
            count = c.fetchone()[0]
            
            # Verificar se já houve atualização automática hoje
            c.execute("""
                SELECT COUNT(*) FROM logs_aum 
                WHERE fonte = 'OCTAV_API' 
                AND tipo = 'ATUALIZACAO_AUTOMATICA'
                AND DATE(timestamp) = ?
                AND status = 'SUCESSO'
            """, (today,))
            auto_count = c.fetchone()[0]
            
            # Atualizar se não há registro para hoje OU se não houve atualização automática hoje
            return count == 0 or auto_count == 0
            
        except Exception as e:
            logger.error(f"Erro ao verificar necessidade de atualização: {str(e)}")
            return True  # Em caso de erro, tentar atualizar
        finally:
            conn.close()

def test_octav_integration():
    """Função para testar a integração com a API Octav"""
    
    # Configurações (substitua pelos valores reais)
    API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwczovL2hhc3VyYS5pby9qd3QvY2xhaW1zIjp7IngtaGFzdXJhLWRlZmF1bHQtcm9sZSI6InVzZXIiLCJ4LWhhc3VyYS1hbGxvd2VkLXJvbGVzIjpbInVzZXIiXSwieC1oYXN1cmEtdXNlci1pZCI6InNhbnJlbW8yNjE0MSJ9fQ.0eLf5m4kQPETnUaZbN6LFMoV8hxGwjrdZ598r9o61Yc"
    WALLET_ADDRESS = "0x3FfDb6ea2084d2BDD62F434cA6B5F610Fa2730aB"
    DB_PATH = "/home/ubuntu/fundo_usdt.db"
    
    # Inicializar API
    octav_api = OctavAPI(API_TOKEN, WALLET_ADDRESS)
    
    # Testar busca de dados
    print("Testando API Octav...")
    portfolio_data = octav_api.get_historical_portfolio()
    
    if portfolio_data:
        networth = octav_api.extract_networth(portfolio_data)
        print(f"✅ Dados obtidos com sucesso!")
        print(f"Valor do portfólio: ${networth:,.2f} USD")
        
        # Testar atualização do AUM
        updater = FundAUMUpdater(DB_PATH, octav_api)
        success, message, data = updater.update_aum_from_octav()
        
        if success:
            print(f"✅ {message}")
            print(f"Dados: {data}")
        else:
            print(f"❌ {message}")
    else:
        print("❌ Erro ao obter dados da API")

if __name__ == "__main__":
    test_octav_integration()

