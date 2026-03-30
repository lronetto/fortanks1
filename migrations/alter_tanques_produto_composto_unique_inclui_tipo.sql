-- =============================================================================
-- Migração MySQL: TanquesProdutoComposto — unique por (tanque, produto, tipo)
-- =============================================================================
-- Objetivo: permitir o mesmo produto composto vinculado a mais de um tipo de peça
--          no mesmo tanque (antes: UNIQUE só em tanque_id + produto_composto_id).
--
-- Compatível: MySQL 5.7 / 8.0+ (InnoDB)
--
-- Antes de rodar a PARTE 2, execute a PARTE 1 e confira se retorna 0 linhas.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- PARTE 1 — Verificação (duplicatas que impediriam o novo UNIQUE)
-- Deve retornar 0 linhas. Se retornar linhas, corrija os dados antes de continuar.
-- -----------------------------------------------------------------------------
SELECT
    `tanque_id`,
    `produto_composto_id`,
    `tipo_peca`,
    COUNT(*) AS qtd
FROM `TanquesProdutoComposto`
GROUP BY `tanque_id`, `produto_composto_id`, `tipo_peca`
HAVING COUNT(*) > 1;

-- -----------------------------------------------------------------------------
-- PARTE 2 — Aplicar migração (índice antigo → novo)
-- -----------------------------------------------------------------------------
ALTER TABLE `TanquesProdutoComposto` DROP INDEX `uq_tanque_produto_composto`;

ALTER TABLE `TanquesProdutoComposto`
  ADD UNIQUE KEY `uq_tanque_produto_composto_tipo` (`tanque_id`, `produto_composto_id`, `tipo_peca`);

-- -----------------------------------------------------------------------------
-- PARTE 3 — (Opcional) Conferir se o novo índice existe
-- -----------------------------------------------------------------------------
-- SHOW INDEX FROM `TanquesProdutoComposto` WHERE Key_name = 'uq_tanque_produto_composto_tipo';
