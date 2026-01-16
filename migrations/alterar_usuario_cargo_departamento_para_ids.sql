-- Script SQL para migrar dados das colunas 'cargo' e 'departamento' (VARCHAR)
-- para as colunas 'cargo_id' e 'departamento_id' (INT/Foreign Keys)
-- 
-- IMPORTANTE: As colunas cargo_id e departamento_id já existem no banco
-- Este script apenas migra os dados baseado nos nomes
-- 
-- Data: 2026-01-16
-- Descrição: Migração de dados de campos de texto para Foreign Keys

-- PASSO 1: Verificar valores atuais antes da migração
SELECT DISTINCT cargo FROM usuarios WHERE cargo IS NOT NULL;
SELECT DISTINCT departamento FROM usuarios WHERE departamento IS NOT NULL;

-- Verificar estado atual das colunas
SELECT 
    COUNT(*) as total,
    COUNT(cargo_id) as tem_cargo_id,
    COUNT(departamento_id) as tem_departamento_id,
    COUNT(cargo) as tem_cargo_nome,
    COUNT(departamento) as tem_departamento_nome
FROM usuarios;

-- PASSO 2: Migrar dados de cargo (nome) para cargo_id
-- Atualizar cargo_id baseado no nome do cargo
UPDATE usuarios u
INNER JOIN cargos c ON c.nome = u.cargo AND c.status = 'Ativo'
SET u.cargo_id = c.id
WHERE u.cargo IS NOT NULL AND u.cargo != '';

-- PASSO 3: Migrar dados de departamento (nome) para departamento_id
-- Atualizar departamento_id baseado no nome do departamento
UPDATE usuarios u
INNER JOIN departamentos d ON d.nome = u.departamento AND d.status = 'Ativo'
SET u.departamento_id = d.id
WHERE u.departamento IS NOT NULL AND u.departamento != '';

-- PASSO 4: Verificar se todos os registros foram migrados
SELECT 
    COUNT(*) as total,
    COUNT(cargo_id) as cargos_migrados,
    COUNT(departamento_id) as departamentos_migrados,
    COUNT(*) - COUNT(cargo_id) as cargos_nao_migrados,
    COUNT(*) - COUNT(departamento_id) as departamentos_nao_migrados
FROM usuarios;

-- PASSO 5: Ver registros que não foram migrados (se houver)
-- Estes registros precisarão ser corrigidos manualmente
SELECT 
    id, 
    nome, 
    email, 
    cargo as cargo_nome_antigo, 
    departamento as departamento_nome_antigo,
    cargo_id,
    departamento_id
FROM usuarios
WHERE (cargo IS NOT NULL AND cargo_id IS NULL) 
   OR (departamento IS NOT NULL AND departamento_id IS NULL);

-- PASSO 6: Verificar integridade dos dados migrados
SELECT 
    u.id,
    u.nome,
    u.cargo as cargo_nome_antigo,
    c.nome as cargo_nome_atual,
    u.departamento as dept_nome_antigo,
    d.nome as dept_nome_atual
FROM usuarios u
LEFT JOIN cargos c ON c.id = u.cargo_id
LEFT JOIN departamentos d ON d.id = u.departamento_id
LIMIT 10;

-- PASSO 7: Se todos os registros foram migrados com sucesso, 
-- você pode remover as colunas antigas (cargo e departamento) se desejar:
-- ATENÇÃO: Execute apenas se tiver certeza de que todos os dados foram migrados!

-- ALTER TABLE usuarios DROP COLUMN cargo;
-- ALTER TABLE usuarios DROP COLUMN departamento;

-- PASSO 8: Verificar se as Foreign Keys estão configuradas
-- Se não estiverem, adicione-as:
-- ALTER TABLE usuarios 
-- ADD CONSTRAINT fk_usuario_cargo FOREIGN KEY (cargo_id) REFERENCES cargos(id);
-- ALTER TABLE usuarios 
-- ADD CONSTRAINT fk_usuario_departamento FOREIGN KEY (departamento_id) REFERENCES departamentos(id);

-- Verificar estrutura final
DESCRIBE usuarios;

-- Nota: Após executar este script, reinicie a aplicação Flask
-- O modelo Python já foi atualizado para usar cargo_id e departamento_id
