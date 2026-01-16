-- Script SQL para criar Foreign Keys (vínculos) entre usuarios e cargos/departamentos
-- 
-- IMPORTANTE: Execute este script manualmente no MySQL
-- 
-- Data: 2026-01-16
-- Descrição: Criar Foreign Keys para garantir integridade referencial

-- PASSO 1: Verificar se as colunas existem
SELECT 
    COLUMN_NAME, 
    DATA_TYPE, 
    IS_NULLABLE,
    COLUMN_KEY
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'usuarios'
  AND COLUMN_NAME IN ('cargo_id', 'departamento_id');

-- PASSO 2: Verificar se já existem Foreign Keys
SELECT 
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'usuarios'
  AND COLUMN_NAME IN ('cargo_id', 'departamento_id')
  AND REFERENCED_TABLE_NAME IS NOT NULL;

-- PASSO 3: Verificar integridade dos dados antes de criar as Foreign Keys
-- Verificar se há registros com cargo_id ou departamento_id inválidos
SELECT 
    COUNT(*) as total_usuarios,
    COUNT(CASE WHEN cargo_id IS NOT NULL THEN 1 END) as com_cargo_id,
    COUNT(CASE WHEN departamento_id IS NOT NULL THEN 1 END) as com_departamento_id,
    COUNT(CASE WHEN cargo_id IS NOT NULL AND cargo_id NOT IN (SELECT id FROM cargos) THEN 1 END) as cargo_id_invalidos,
    COUNT(CASE WHEN departamento_id IS NOT NULL AND departamento_id NOT IN (SELECT id FROM departamentos) THEN 1 END) as departamento_id_invalidos
FROM usuarios;

-- PASSO 4: Listar registros com IDs inválidos (se houver)
SELECT 
    u.id,
    u.nome,
    u.email,
    u.cargo_id,
    u.departamento_id,
    CASE WHEN c.id IS NULL THEN 'INVÁLIDO' ELSE 'OK' END as status_cargo,
    CASE WHEN d.id IS NULL THEN 'INVÁLIDO' ELSE 'OK' END as status_departamento
FROM usuarios u
LEFT JOIN cargos c ON c.id = u.cargo_id
LEFT JOIN departamentos d ON d.id = u.departamento_id
WHERE c.id IS NULL OR d.id IS NULL;

-- PASSO 5: Remover Foreign Keys existentes (se houver) antes de criar novas
-- Descomente as linhas abaixo se precisar remover Foreign Keys existentes
-- ALTER TABLE usuarios DROP FOREIGN KEY IF EXISTS fk_usuario_cargo;
-- ALTER TABLE usuarios DROP FOREIGN KEY IF EXISTS fk_usuario_departamento;

-- PASSO 6: Criar Foreign Key para cargo_id
-- Verificar se a constraint já existe antes de criar
SET @fk_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'usuarios'
      AND CONSTRAINT_NAME = 'fk_usuario_cargo'
);

SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE usuarios ADD CONSTRAINT fk_usuario_cargo FOREIGN KEY (cargo_id) REFERENCES cargos(id) ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT "Foreign Key fk_usuario_cargo já existe" as mensagem'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- PASSO 7: Criar Foreign Key para departamento_id
SET @fk_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'usuarios'
      AND CONSTRAINT_NAME = 'fk_usuario_departamento'
);

SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE usuarios ADD CONSTRAINT fk_usuario_departamento FOREIGN KEY (departamento_id) REFERENCES departamentos(id) ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT "Foreign Key fk_usuario_departamento já existe" as mensagem'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- PASSO 8: Verificar se as Foreign Keys foram criadas com sucesso
SELECT 
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r 
    ON k.CONSTRAINT_NAME = r.CONSTRAINT_NAME
WHERE k.TABLE_SCHEMA = DATABASE()
  AND k.TABLE_NAME = 'usuarios'
  AND k.COLUMN_NAME IN ('cargo_id', 'departamento_id')
  AND k.REFERENCED_TABLE_NAME IS NOT NULL;

-- PASSO 9: Verificar estrutura final da tabela
DESCRIBE usuarios;

-- Nota: 
-- ON DELETE RESTRICT: Impede a exclusão de um cargo/departamento se houver usuários vinculados
-- ON UPDATE CASCADE: Atualiza automaticamente o ID se o ID do cargo/departamento for alterado
