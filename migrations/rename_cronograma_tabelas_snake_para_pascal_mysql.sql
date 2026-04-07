-- Renomeia tabelas antigas (snake_case) para o padrão PascalCase.
-- Execute com backup. Se já estiver em PascalCase, não execute.

SET FOREIGN_KEY_CHECKS = 0;

RENAME TABLE cronograma_feriados TO CronogramaFeriados;
RENAME TABLE cronograma_tanques TO CronogramaTanques;
RENAME TABLE cronograma_linhas_base TO CronogramaLinhasBase;
RENAME TABLE cronograma_linhas_base_tanques TO CronogramaLinhasBaseTanques;
RENAME TABLE cronograma_itens TO CronogramaItens;

SET FOREIGN_KEY_CHECKS = 1;

-- Nota: em versões recentes do InnoDB as FKs são atualizadas ao renomear.
-- Se algum erro ocorrer, recrie as FKs apontando para os novos nomes.
