-- Migração: UnidadesConversao - remover material_id e adicionar dados_adicionais (JSON materiais)
-- Execute conforme seu banco (MySQL/MariaDB ou SQLite 3.35+).

-- MySQL / MariaDB:
-- ALTER TABLE UnidadesConversao ADD COLUMN dados_adicionais TEXT NULL AFTER unidade_destino_id;
-- ALTER TABLE UnidadesConversao DROP FOREIGN KEY <nome_da_fk_se_existir>;
-- ALTER TABLE UnidadesConversao DROP COLUMN material_id;

-- SQLite (3.35+):
-- ALTER TABLE UnidadesConversao ADD COLUMN dados_adicionais TEXT;
-- ALTER TABLE UnidadesConversao DROP COLUMN material_id;

-- Exemplo genérico: adicionar coluna (execute primeiro)
ALTER TABLE UnidadesConversao ADD COLUMN dados_adicionais TEXT NULL;

-- Remover material_id: no MySQL remova a FK antes; no SQLite 3.35+ pode usar DROP COLUMN.
-- Se sua versão do SQLite for anterior a 3.35, será necessário recriar a tabela sem a coluna.
