-- =====================================================
-- Script SQL para Verificação de Dados Duplicados
-- Tabela: Uploads
-- =====================================================

-- 1. Verificar duplicatas completas (pai, pai_id, tipo, filename, mimetype)
-- Esta é a verificação mais rigorosa, baseada na lógica do __init__ (linha 34)
-- Retorna registros que têm exatamente os mesmos valores para todos esses campos
SELECT 
    pai,
    pai_id,
    tipo,
    filename,
    mimetype,
    COUNT(*) as quantidade,
    GROUP_CONCAT(id ORDER BY id SEPARATOR ', ') as ids_duplicados,
    GROUP_CONCAT(uploaded_at ORDER BY uploaded_at SEPARATOR ' | ') as datas_upload
FROM Uploads
WHERE pai IS NOT NULL 
  AND pai_id IS NOT NULL 
  AND tipo IS NOT NULL
GROUP BY pai, pai_id, tipo, filename, mimetype
HAVING COUNT(*) > 1
ORDER BY quantidade DESC, filename;

-- 2. Verificar duplicatas apenas por filename
-- Baseado na verificação da linha 50 do código
SELECT 
    filename,
    COUNT(*) as quantidade,
    GROUP_CONCAT(id ORDER BY id SEPARATOR ', ') as ids_duplicados,
    GROUP_CONCAT(CONCAT('ID:', id, ' | Pai:', IFNULL(pai, 'NULL'), ' | Tipo:', IFNULL(tipo, 'NULL')) SEPARATOR ' | ') as detalhes
FROM Uploads
GROUP BY filename
HAVING COUNT(*) > 1
ORDER BY quantidade DESC, filename;

-- 3. Verificar duplicatas por filename e mimetype
-- Útil para identificar arquivos com mesmo nome e tipo MIME
SELECT 
    filename,
    mimetype,
    COUNT(*) as quantidade,
    GROUP_CONCAT(id ORDER BY id SEPARATOR ', ') as ids_duplicados,
    GROUP_CONCAT(CONCAT('ID:', id, ' | Pai:', IFNULL(pai, 'NULL'), ' | PaiID:', IFNULL(pai_id, 'NULL')) SEPARATOR ' | ') as detalhes
FROM Uploads
GROUP BY filename, mimetype
HAVING COUNT(*) > 1
ORDER BY quantidade DESC, filename;

-- 4. Verificar duplicatas por contexto (pai, pai_id, tipo)
-- Identifica múltiplos uploads no mesmo contexto
SELECT 
    pai,
    pai_id,
    tipo,
    COUNT(*) as quantidade,
    GROUP_CONCAT(id ORDER BY id SEPARATOR ', ') as ids_duplicados,
    GROUP_CONCAT(filename SEPARATOR ', ') as arquivos
FROM Uploads
WHERE pai IS NOT NULL 
  AND pai_id IS NOT NULL 
  AND tipo IS NOT NULL
GROUP BY pai, pai_id, tipo
HAVING COUNT(*) > 1
ORDER BY quantidade DESC, pai, pai_id;

-- 5. Verificar duplicatas considerando NULLs (versão mais flexível)
-- Trata NULL como valor válido para comparação
SELECT 
    IFNULL(pai, 'NULL') as pai,
    IFNULL(pai_id, 'NULL') as pai_id,
    IFNULL(tipo, 'NULL') as tipo,
    filename,
    mimetype,
    COUNT(*) as quantidade,
    GROUP_CONCAT(id ORDER BY id SEPARATOR ', ') as ids_duplicados
FROM Uploads
GROUP BY pai, pai_id, tipo, filename, mimetype
HAVING COUNT(*) > 1
ORDER BY quantidade DESC, filename;

-- 6. Resumo geral de duplicatas
-- Mostra estatísticas gerais sobre duplicatas
SELECT 
    'Duplicatas Completas (pai, pai_id, tipo, filename, mimetype)' as tipo_duplicata,
    COUNT(*) as total_grupos_duplicados,
    SUM(quantidade) as total_registros_duplicados
FROM (
    SELECT 
        pai, pai_id, tipo, filename, mimetype,
        COUNT(*) as quantidade
    FROM Uploads
    WHERE pai IS NOT NULL AND pai_id IS NOT NULL AND tipo IS NOT NULL
    GROUP BY pai, pai_id, tipo, filename, mimetype
    HAVING COUNT(*) > 1
) as dup_completas

UNION ALL

SELECT 
    'Duplicatas por Filename' as tipo_duplicata,
    COUNT(*) as total_grupos_duplicados,
    SUM(quantidade) as total_registros_duplicados
FROM (
    SELECT 
        filename,
        COUNT(*) as quantidade
    FROM Uploads
    GROUP BY filename
    HAVING COUNT(*) > 1
) as dup_filename;

-- 7. Detalhamento de registros duplicados com informações completas
-- Útil para análise detalhada antes de remover duplicatas
SELECT 
    u1.id,
    u1.pai,
    u1.pai_id,
    u1.tipo,
    u1.filename,
    u1.mimetype,
    u1.uploaded_at,
    u1.data,
    (SELECT COUNT(*) 
     FROM Uploads u2 
     WHERE u2.pai = u1.pai 
       AND u2.pai_id = u1.pai_id 
       AND u2.tipo = u1.tipo 
       AND u2.filename = u1.filename 
       AND u2.mimetype = u1.mimetype
       AND u2.id < u1.id) as tem_duplicata_anterior
FROM Uploads u1
WHERE EXISTS (
    SELECT 1 
    FROM Uploads u2 
    WHERE u2.pai = u1.pai 
      AND u2.pai_id = u1.pai_id 
      AND u2.tipo = u1.tipo 
      AND u2.filename = u1.filename 
      AND u2.mimetype = u1.mimetype
      AND u2.id != u1.id
)
ORDER BY u1.pai, u1.pai_id, u1.tipo, u1.filename, u1.id;

-- 8. Identificar registros duplicados mantendo apenas o mais antigo
-- Útil para identificar quais registros podem ser removidos (manter o primeiro)
SELECT 
    u1.id as id_para_remover,
    u1.pai,
    u1.pai_id,
    u1.tipo,
    u1.filename,
    u1.mimetype,
    u1.uploaded_at,
    (SELECT MIN(id) 
     FROM Uploads u2 
     WHERE u2.pai = u1.pai 
       AND u2.pai_id = u1.pai_id 
       AND u2.tipo = u1.tipo 
       AND u2.filename = u1.filename 
       AND u2.mimetype = u1.mimetype) as id_manter
FROM Uploads u1
WHERE u1.pai IS NOT NULL 
  AND u1.pai_id IS NOT NULL 
  AND u1.tipo IS NOT NULL
  AND u1.id > (
      SELECT MIN(id) 
      FROM Uploads u2 
      WHERE u2.pai = u1.pai 
        AND u2.pai_id = u1.pai_id 
        AND u2.tipo = u1.tipo 
        AND u2.filename = u1.filename 
        AND u2.mimetype = u1.mimetype
  )
ORDER BY u1.pai, u1.pai_id, u1.tipo, u1.filename, u1.id;

-- =====================================================
-- QUERIES PARA LIMPEZA (USE COM CUIDADO!)
-- =====================================================

-- 9. Query para remover duplicatas mantendo apenas o registro mais antigo
-- ATENÇÃO: Faça backup antes de executar!
-- Descomente apenas após revisar os resultados das queries acima
/*
DELETE u1 FROM Uploads u1
INNER JOIN Uploads u2 
WHERE u1.pai = u2.pai 
  AND u1.pai_id = u2.pai_id 
  AND u1.tipo = u2.tipo 
  AND u1.filename = u2.filename 
  AND u1.mimetype = u2.mimetype
  AND u1.pai IS NOT NULL 
  AND u1.pai_id IS NOT NULL 
  AND u1.tipo IS NOT NULL
  AND u1.id > u2.id;
*/

-- 10. Query para remover duplicatas por filename mantendo apenas o primeiro
-- ATENÇÃO: Faça backup antes de executar!
/*
DELETE u1 FROM Uploads u1
INNER JOIN Uploads u2 
WHERE u1.filename = u2.filename 
  AND u1.id > u2.id;
*/


