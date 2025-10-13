# 🚀 Sistema Fortanks - Funcionamento Offline

## ✅ Status dos Scripts
Todos os scripts foram criados e testados com sucesso! O sistema está pronto para funcionamento offline.

## 📋 Scripts Criados

1. **`scripts/setup_offline.py`** - Script principal (RECOMENDADO)
2. **`scripts/migrar_para_sqlite.py`** - Migração completa MySQL → SQLite
3. **`scripts/sincronizar_sqlite.py`** - Sincronização incremental
4. **`scripts/configurar_modo_offline.py`** - Configuração offline/online
5. **`scripts/testar_scripts_simples.py`** - Teste dos scripts

## 🚀 Como Usar (Método Rápido)

### 1. Executar Setup Completo
```bash
python scripts/setup_offline.py
```
- Escolha a opção **6** (Setup completo)
- Isso fará a migração completa + configuração offline

### 2. Reiniciar a Aplicação
```bash
python app.py
```

## 🔄 Sincronização Periódica

Para manter o banco local atualizado:
```bash
python scripts/sincronizar_sqlite.py
```

## ⚙️ Alternar Entre Modos

### Para Modo Offline:
```bash
python scripts/configurar_modo_offline.py
# Escolha opção 1
```

### Para Modo Online:
```bash
python scripts/configurar_modo_offline.py
# Escolha opção 2
```

## 📁 Arquivos Importantes

- **Banco SQLite:** `instance/fortanks_offline.db`
- **Configuração:** `config/config.py`
- **Backups:** `config/config_backup_*.py`
- **Logs:** `logs/migracao_sqlite.log` e `logs/sincronizacao_sqlite.log`

## ⚠️ Considerações

### Modo Offline:
- ✅ Dados locais funcionam normalmente
- ❌ E-mail não funcionará
- ❌ API Arquivei não funcionará
- ❌ Não há sincronização automática

### Recomendações:
1. Execute sincronização incremental diariamente
2. Mantenha backups do banco SQLite
3. Teste antes de usar em produção

## 🆘 Troubleshooting

### Se a migração falhar:
1. Verifique conexão com MySQL
2. Confirme credenciais no `.env`
3. Execute: `python scripts/testar_scripts_simples.py`

### Se o sistema não iniciar:
1. Verifique se o banco SQLite existe
2. Confirme configuração em `config/config.py`
3. Verifique logs em `logs/`

## 📞 Suporte

- **Logs:** Sempre verifique os logs em `logs/`
- **Testes:** Execute `python scripts/testar_scripts_simples.py`
- **Documentação:** Consulte `scripts/README_OFFLINE.md`

---

**🎉 Sistema pronto para funcionamento offline!**


