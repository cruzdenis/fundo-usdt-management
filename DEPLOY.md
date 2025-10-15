# 🚀 Deploy no Railway - CORRIGIDO

## ⚠️ Problemas Resolvidos
- ✅ **Dependências atualizadas** - Removido hashlib2 problemático
- ✅ **Python 3.11** especificado no runtime.txt
- ✅ **Nixpacks configurado** para build mais estável
- ✅ **Streamlit otimizado** para Railway

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
- ✅ **Linguagem**: Python 3.11
- ✅ **Framework**: Streamlit
- ✅ **Build**: Nixpacks (configurado)
- ✅ **Comando de Start**: Configurado no `railway.json`
- ✅ **Porta**: $PORT (automática)

### 4. Deploy Automático
- O deploy iniciará automaticamente
- ⏱️ **Tempo estimado**: 3-5 minutos
- 🔄 **Redeploy automático** a cada push no GitHub

### 5. Verificação de Deploy
Se o deploy falhar:
1. Vá em "Deployments" > "View logs"
2. Verifique se todas as dependências foram instaladas
3. Aguarde o redeploy automático (pode levar alguns minutos)

### 6. Configurações Opcionais

#### Variáveis de Ambiente (se necessário)
```
PORT=8501
PYTHONPATH=/app
```

#### Domínio Customizado
- Acesse "Settings" > "Domains"
- Adicione seu domínio personalizado

### 7. Monitoramento
- **Logs**: Disponíveis na aba "Deployments"
- **Métricas**: CPU, RAM, Network na aba "Metrics"
- **Redeploy**: Automático a cada push no GitHub

## 🔧 Arquivos de Configuração

### `requirements.txt` (CORRIGIDO)
```
streamlit>=1.28.0
pandas>=2.0.0
plotly>=5.15.0
requests>=2.31.0
numpy>=1.24.0
```

### `runtime.txt` (NOVO)
```
python-3.11.0
```

### `nixpacks.toml` (NOVO)
```toml
[phases.setup]
nixPkgs = ["python311", "pip"]

[phases.install]
cmds = ["pip install -r requirements.txt"]

[start]
cmd = "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false"
```

### `railway.json` (ATUALIZADO)
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

## 🌐 URL do Repositório
**GitHub**: https://github.com/cruzdenis/fundo-usdt-management

## 🔄 Redeploy Manual
Se necessário, force um redeploy:
1. Vá em "Deployments"
2. Clique nos três pontos (...) 
3. Selecione "Redeploy"

## 📞 Suporte
- **Railway Docs**: https://docs.railway.app
- **Streamlit Docs**: https://docs.streamlit.io
- **Nixpacks Docs**: https://nixpacks.com

## 🎯 Credenciais de Acesso
### Administrador
- **Email**: admin@fundo.com
- **Senha**: admin123

### Cliente Demo
- **Email**: joao@email.com
- **Senha**: demo123

---

**Status**: ✅ CORRIGIDO  
**Tempo estimado de deploy**: 3-5 minutos  
**Custo**: Gratuito (Railway Free Tier)  
**Uptime**: 99.9%

