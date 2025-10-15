# 🏦 Fundo USDT - Sistema de Gestão de Investimentos

Sistema completo de gestão de fundo de investimento com integração à API Octav.fi para monitoramento automático de portfólio.

## 🚀 Funcionalidades

- **📊 Dashboard Administrativo Completo**
- **👥 Gestão de Clientes e Investidores**
- **💰 Controle de AUM (Assets Under Management)**
- **🔄 Integração com API Octav.fi**
- **📈 Relatórios e Análises Detalhadas**
- **⚙️ Configurações Avançadas**

## 🔐 Credenciais de Acesso

### Administrador
- **Email**: admin@fundo.com
- **Senha**: admin123

### Cliente Demo
- **Email**: joao@email.com
- **Senha**: demo123

## 🔧 Tecnologias Utilizadas

- **Streamlit** - Interface web interativa
- **Pandas** - Manipulação de dados
- **Plotly** - Gráficos e visualizações
- **SQLite** - Banco de dados
- **Octav.fi API** - Monitoramento de portfólio

## 📊 Integração Octav.fi

O sistema monitora automaticamente a wallet:
`0x3FfDb6ea2084d2BDD62F434cA6B5F610Fa2730aB`

### Funcionalidades da Integração:
- ✅ Atualização automática diária do AUM
- ✅ Cálculo automático do valor da cota
- ✅ Monitoramento em tempo real do portfólio
- ✅ Logs detalhados de operações

## 🚀 Deploy

### Railway
Este projeto está configurado para deploy automático no Railway.

### Variáveis de Ambiente
Não são necessárias variáveis de ambiente adicionais - todas as configurações estão incluídas no código.

## 📱 Como Usar

1. **Acesse o sistema** através do URL de deploy
2. **Faça login** com as credenciais fornecidas
3. **Navegue pelas abas** para acessar diferentes funcionalidades:
   - **AUM Diário**: Controle manual e automático do AUM
   - **Clientes**: Gestão de investidores
   - **Movimentações**: Registro de investimentos e resgates
   - **Octav API**: Configurações de integração
   - **Configurações**: Parâmetros do fundo

## 🔄 Fluxo de Investimentos

1. **Atualize o AUM** (manual ou automático via Octav.fi)
2. **Registre a movimentação** do cliente
3. **Sistema calcula automaticamente** as cotas baseadas no valor atual
4. **Acompanhe** a evolução através dos relatórios

## 📈 Relatórios Disponíveis

- **Evolução do AUM** ao longo do tempo
- **Performance mensal** do fundo
- **Distribuição de clientes** por valor investido
- **Histórico completo** de movimentações

## 🛠️ Desenvolvimento

Para executar localmente:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 📞 Suporte

Sistema desenvolvido para gestão profissional de fundos de investimento com foco em transparência e automação.

---

**Versão**: 2.0  
**Última atualização**: Outubro 2024

