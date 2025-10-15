# 🚀 Deploy no Railway

## Passos para Deploy

### 1. Acesse o Railway
- Vá para [railway.app](https://railway.app)
- Faça login com sua conta GitHub

### 2. Crie um Novo Projeto
- Clique em "New Project"
- Selecione "Deploy from GitHub repo"
- Escolha o repositório: `cruzdenis/fundo-usdt-management`

### 3. Configurações Automáticas
O Railway detectará automaticamente:
- ✅ **Linguagem**: Python
- ✅ **Framework**: Streamlit
- ✅ **Comando de Start**: Configurado no `railway.json`
- ✅ **Porta**: $PORT (automática)

### 4. Deploy Automático
- O deploy iniciará automaticamente
- Aguarde a conclusão (aproximadamente 2-3 minutos)
- O Railway fornecerá uma URL pública

### 5. Configurações Opcionais

#### Variáveis de Ambiente (se necessário)
```
PORT=8501
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_ENABLE_CORS=false
```

#### Domínio Customizado
- Acesse "Settings" > "Domains"
- Adicione seu domínio personalizado

### 6. Monitoramento
- **Logs**: Disponíveis na aba "Deployments"
- **Métricas**: CPU, RAM, Network na aba "Metrics"
- **Redeploy**: Automático a cada push no GitHub

## 🔧 Arquivos de Configuração

### `railway.json`
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### `Procfile`
```
web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
```

### `requirements.txt`
```
streamlit==1.28.0
pandas==2.0.3
plotly==5.15.0
requests==2.31.0
numpy==1.24.3
hashlib2==1.0.1
```

## 🌐 URL do Repositório
**GitHub**: https://github.com/cruzdenis/fundo-usdt-management

## 📞 Suporte
- **Railway Docs**: https://docs.railway.app
- **Streamlit Docs**: https://docs.streamlit.io

---

**Tempo estimado de deploy**: 2-3 minutos  
**Custo**: Gratuito (Railway Free Tier)  
**Uptime**: 99.9%

