# Plano de migracao MySQL -> PostgreSQL (Fortanks)

## Objetivo

Migrar o banco principal de producao de MySQL para PostgreSQL com baixo risco e possibilidade de rollback rapido.

## Premissas

- Aplicacao atual usa SQLAlchemy (`config/config.py`) e aceita `DATABASE_URI`.
- Banco atual e MySQL.
- Mudanca sera feita em janela controlada.

## Fase 1 - Preparacao (sem impacto em producao)

1. Criar banco PostgreSQL vazio (mesmo schema logico do MySQL).
2. Configurar usuario com privilegios de `CREATE`, `ALTER`, `INSERT`, `UPDATE`, `DELETE`.
3. Definir variaveis de ambiente:
   - `MIGRACAO_MYSQL_URI`
   - `MIGRACAO_POSTGRES_URI`
4. Rodar script de migracao em homologacao:
   - `python scripts/migrar_mysql_para_postgres.py`
5. Rodar validacao:
   - `python scripts/validar_migracao_postgres.py`
6. Corrigir incompatibilidades encontradas (tipos, constraints, defaults, indices).

## Fase 2 - Testes de aplicacao

1. Subir app apontando para PostgreSQL via `DATABASE_URI`.
2. Executar testes automatizados (`pytest`) e smoke tests manuais.
3. Validar fluxos criticos:
   - login/permissoes
   - cadastros principais
   - relatorios de maior uso
   - rotinas agendadas e backups

## Fase 3 - Cutover de producao

1. Congelar escrita no MySQL (janela de manutencao).
2. Executar migracao final MySQL -> PostgreSQL.
3. Executar validacao final (contagem e amostragem).
4. Trocar `DATABASE_URI` da aplicacao para PostgreSQL.
5. Monitorar erros, latencia e locks por 24h.

## Rollback

Se houver erro funcional grave apos o cutover:

1. Restaurar `DATABASE_URI` para MySQL.
2. Reiniciar aplicacao.
3. Reabrir escrita no MySQL.
4. Registrar divergencias e repetir ciclo em homologacao.

## Riscos conhecidos

- Tipos especificos de MySQL (`enum`, `tinyint(1)`, `datetime` sem timezone).
- SQL nativo com funcoes MySQL (`ifnull`, `date_format`, etc).
- Diferencas de collate/charset.
- Constraints e indices gerados de forma diferente entre dialetos.

## Checklist rapido de go-live

- [ ] Backup do MySQL concluido e validado
- [ ] Banco PostgreSQL preparado
- [ ] Migracao final executada sem erro
- [ ] Validacao de contagem e amostragem concluida
- [ ] Aplicacao testada em PostgreSQL
- [ ] Plano de rollback pronto
