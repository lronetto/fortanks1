-- =============================================================================
-- Renomear tabelas do módulo de equipamentos (MySQL / InnoDB)
--
-- Mapeamento:
--   equipamentos            -> Equipamentos
--   manutencoes             -> EquipamentosManutencoes
--   equipamento_emprestimos -> EquipamentosEmprestimos
--   checklist_modelos       -> EquipamentosChecklistModelos
--   checklist_itens         -> EquipamentosChecklistItens
--   checklist_equipamentos  -> EquipamentosChecklistRegistros
--   checklist_respostas     -> EquipamentosChecklistRespostas
--
-- Depois de executar: faça deploy do código com models/equipamento.py atualizado.
--
-- IMPORTANTE:
-- 1) Backup completo antes de executar.
-- 2) Pare a aplicação durante a migração.
-- 3) Em Linux com lower_case_table_names=1, o MySQL pode gravar nomes em minúsculas;
--    confira SHOW TABLES; e alinhe __tablename__ no SQLAlchemy se necessário.
-- 4) Se equipamento_emprestimos não existir, comente a linha correspondente no RENAME TABLE;
--    o bloco "Criação" abaixo cria EquipamentosEmprestimos com IF NOT EXISTS.
-- 5) Ordem: primeiro RENAME (para existir a tabela Equipamentos), depois CREATE empréstimos.
-- =============================================================================
CREATE TABLE IF NOT EXISTS `EquipamentosEmprestimos` (
    `id` int NOT NULL AUTO_INCREMENT,
    `equipamento_id` int NOT NULL,
    `colaborador_id` int NOT NULL,
    `data_entrega` datetime NOT NULL,
    `data_recebimento` datetime DEFAULT NULL,
    `observacoes` text DEFAULT NULL,
    `usuario_registro_id` int DEFAULT NULL,
    `data_cadastro` datetime DEFAULT NULL,
    `data_atualizacao` datetime DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `ix_EquipamentosEmprestimos_equipamento` (`equipamento_id`),
    KEY `ix_EquipamentosEmprestimos_colaborador` (`colaborador_id`),
    KEY `ix_EquipamentosEmprestimos_usuario` (`usuario_registro_id`),
    CONSTRAINT `fk_EquipamentosEmprestimos_equipamento`
        FOREIGN KEY (`equipamento_id`) REFERENCES `Equipamentos` (`id`),
    CONSTRAINT `fk_EquipamentosEmprestimos_colaborador`
        FOREIGN KEY (`colaborador_id`) REFERENCES `colaboradores` (`id`),
    CONSTRAINT `fk_EquipamentosEmprestimos_usuario`
        FOREIGN KEY (`usuario_registro_id`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @OLD_SQL_MODE = @@SQL_MODE;
SET SQL_MODE = (SELECT REPLACE(@@SQL_MODE, 'NO_ZERO_DATE', ''));

SET FOREIGN_KEY_CHECKS = 0;

-- Renomeação atômica (InnoDB atualiza referências de FK internamente na maioria dos casos)
RENAME TABLE
    `checklist_respostas`      TO `EquipamentosChecklistRespostas`,
    `checklist_equipamentos` TO `EquipamentosChecklistRegistros`,
    `checklist_itens`        TO `EquipamentosChecklistItens`,
    `checklist_modelos`      TO `EquipamentosChecklistModelos`,
    `manutencoes`            TO `EquipamentosManutencoes`,
    `equipamentos`           TO `Equipamentos`;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- Criação: EquipamentosEmprestimos (se ainda não existir)
-- Executa após o RENAME para que a FK aponte para `Equipamentos`.
-- Se você manteve a linha do RENAME de equipamento_emprestimos, esta instrução
-- não faz nada (tabela já existe com o nome novo).
-- =============================================================================


SET SQL_MODE = @OLD_SQL_MODE;

-- =============================================================================
-- Se o MySQL reclamar de FK ou nomes de constraints antigos, use o bloco
-- alternativo abaixo (descomente, ajuste nomes de constraints via
-- information_schema se necessário, execute ANTES do RENAME acima).
-- =============================================================================
/*
-- Listar constraints (ajuste manualmente os nomes retornados):
-- SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME
-- FROM information_schema.KEY_COLUMN_USAGE
-- WHERE TABLE_SCHEMA = DATABASE()
--   AND REFERENCED_TABLE_NAME IN (
--     'equipamentos','manutencoes','equipamento_emprestimos',
--     'checklist_modelos','checklist_itens','checklist_equipamentos','checklist_respostas'
--   );

SET FOREIGN_KEY_CHECKS = 0;
-- Exemplo (substitua pelos nomes reais das constraints no seu banco):
-- ALTER TABLE `manutencoes` DROP FOREIGN KEY `manutencoes_ibfk_1`;
-- ... repetir para todas as FKs que apontam para ou saem dessas tabelas ...
-- RENAME TABLE ...
-- ALTER TABLE `EquipamentosManutencoes` ADD CONSTRAINT `fk_eqman_equipamento`
--   FOREIGN KEY (`equipamento_id`) REFERENCES `Equipamentos` (`id`);
SET FOREIGN_KEY_CHECKS = 1;
*/
