# Sistema Fortanks - Funcionamento Offline

Este conjunto de scripts permite que o sistema Fortanks funcione offline usando um banco SQLite local em vez do MySQL remoto.

## 📋 Pré-requisitos

1. **Dependências Python instaladas:**
   ```bash
   pip install sqlalchemy pymysql pandas python-dotenv
   ```

2. **Arquivo .env configurado** com as credenciais do MySQL:
   ```env
   DB_PASSWORD=sua_senha_mysql
   SECRET_KEY=sua_chave_secreta
   ```

3. **Conexão com o servidor MySQL** (para migração inicial)

## 🚀 Scripts Disponíveis

### 1. `setup_offline.py` - Script Principal
Script orquestrador que facilita todo o processo:
```bash
python scripts/setup_offline.py
```

**Opções disponíveis:**
- Migração completa (MySQL -> SQLite)
- Sincronização incremental
- Configurar modo offline/online
- Verificar status do banco SQLite
- Setup completo (migração + configuração)

### 2. `migrar_para_sqlite.py` - Migração Completa
Migra todos os dados do MySQL para SQLite:
```bash
python scripts/migrar_para_sqlite.py
```

**O que faz:**
- Conecta ao banco MySQL existente
- Cria banco SQLite local (`instance/fortanks_offline.db`)
- Copia estrutura e dados de todas as tabelas
- Cria tabela de controle de sincronização
- Mapeia tipos MySQL para SQLite

### 3. `sincronizar_sqlite.py` - Sincronização Incremental
Sincroniza apenas mudanças desde a última sincronização:
```bash
python scripts/sincronizar_sqlite.py
```

**O que faz:**
- Identifica registros modificados desde última sincronização
- Atualiza apenas dados alterados
- Mantém controle de sincronização
- Mais rápido que migração completa

### 4. `configurar_modo_offline.py` - Configuração
Altera as configurações do sistema:
```bash
python scripts/configurar_modo_offline.py
```

**Opções:**
- Configurar para modo OFFLINE (SQLite)
- Configurar para modo ONLINE (MySQL)
- Verificar status do banco SQLite

## 📖 Guia de Uso

### Primeira Configuração (Setup Completo)

1. **Execute o script principal:**
   ```bash
   python scripts/setup_offline.py
   ```

2. **Escolha a opção 6 (Setup completo)**
   - Isso fará a migração completa
   - Configurará o sistema para modo offline
   - Criará backup da configuração original

3. **Reinicie a aplicação:**
   ```bash
   python app.py
   ```

### Sincronização Periódica

Para manter o banco local atualizado:

1. **Sincronização rápida (recomendada):**
   ```bash
   python scripts/sincronizar_sqlite.py
   ```

2. **Ou use o script principal:**
   ```bash
   python scripts/setup_offline.py
   # Escolha opção 2
   ```

### Voltar ao Modo Online

1. **Execute o configurador:**
   ```bash
   python scripts/configurar_modo_offline.py
   ```

2. **Escolha opção 2 (Configurar para modo ONLINE)**

3. **Reinicie a aplicação**

## 📁 Estrutura de Arquivos

```
fortanks_novo/
├── scripts/
│   ├── setup_offline.py          # Script principal
│   ├── migrar_para_sqlite.py     # Migração completa
│   ├── sincronizar_sqlite.py     # Sincronização incremental
│   ├── configurar_modo_offline.py # Configuração
│   └── README_OFFLINE.md         # Este arquivo
├── instance/
│   └── fortanks_offline.db       # Banco SQLite local
├── config/
│   ├── config.py                 # Configuração atual
│   └── config_backup_*.py        # Backups automáticos
└── logs/
    ├── migracao_sqlite.log       # Logs de migração
    └── sincronizacao_sqlite.log  # Logs de sincronização
```

## 🔧 Configurações

### Modo Offline
- **Banco:** SQLite local (`instance/fortanks_offline.db`)
- **E-mail:** Desabilitado
- **API Arquivei:** Desabilitada
- **Flag:** `MODO_OFFLINE = True`

### Modo Online
- **Banco:** MySQL remoto (`192.168.8.10:3306/sfortanks`)
- **E-mail:** Habilitado
- **API Arquivei:** Habilitada
- **Flag:** `MODO_OFFLINE = False`

## 📊 Monitoramento

### Logs
- **Migração:** `logs/migracao_sqlite.log`
- **Sincronização:** `logs/sincronizacao_sqlite.log`

### Tabela de Controle
O sistema cria uma tabela `controle_sincronizacao` no SQLite com:
- Data da última sincronização por tabela
- Número de registros sincronizados
- Status da sincronização
- Logs de erro

### Verificar Status
```bash
python scripts/setup_offline.py
# Escolha opção 5
```

## ⚠️ Considerações Importantes

### Limitações do Modo Offline
1. **E-mail:** Não funcionará (configurações desabilitadas)
2. **API Arquivei:** Não funcionará (configurações desabilitadas)
3. **Dados:** Apenas dados locais (não há sincronização automática)
4. **Usuários:** Dados de usuários locais

### Recomendações
1. **Sincronização regular:** Execute sincronização incremental diariamente
2. **Backup:** Mantenha backups do banco SQLite
3. **Testes:** Teste o modo offline antes de usar em produção
4. **Monitoramento:** Verifique logs regularmente

### Troubleshooting

**Erro de conexão MySQL:**
- Verifique se o servidor MySQL está acessível
- Confirme credenciais no arquivo `.env`
- Teste conectividade de rede

**Erro de permissão SQLite:**
- Verifique permissões do diretório `instance/`
- Certifique-se de que o processo tem acesso de escrita

**Dados desatualizados:**
- Execute sincronização incremental
- Verifique logs de sincronização
- Considere migração completa se necessário

## 🔄 Fluxo de Trabalho Recomendado

1. **Desenvolvimento/Teste:**
   - Use modo offline para desenvolvimento
   - Sincronize periodicamente com dados de produção

2. **Produção:**
   - Use modo online como padrão
   - Configure modo offline apenas quando necessário
   - Mantenha sincronização regular

3. **Manutenção:**
   - Execute migração completa mensalmente
   - Monitore logs de sincronização
   - Faça backup do banco SQLite

## 📞 Suporte

Em caso de problemas:
1. Verifique os logs em `logs/`
2. Execute verificações de status
3. Considere migração completa se sincronização falhar
4. Mantenha backups das configurações originais


