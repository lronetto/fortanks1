-- Script SQL para alterar a coluna 'cargo' da tabela 'usuarios' de ENUM para VARCHAR
-- Este script resolve o erro: 'TÉCNICO DE EDIFICAÇÕES' is not among the defined enum values
-- 
-- IMPORTANTE: Execute este script manualmente no MySQL antes de reiniciar a aplicação
-- 
-- Data: 2026-01-16
-- Descrição: Migração de ENUM para VARCHAR para suportar cargos dinâmicos do modelo Cargo

-- Verificar valores atuais na coluna cargo antes da alteração
SELECT DISTINCT cargo FROM usuarios;

-- Alterar a coluna cargo de ENUM para VARCHAR(100)
-- Isso permite armazenar qualquer valor de cargo, não apenas os valores do Enum
ALTER TABLE usuarios 
MODIFY COLUMN cargo VARCHAR(100) NOT NULL;

-- Verificar se a alteração foi aplicada corretamente
DESCRIBE usuarios;

-- Verificar se os dados foram preservados
SELECT id, nome, email, cargo FROM usuarios LIMIT 10;

-- Nota: Após executar este script, reinicie a aplicação Flask
-- O modelo Python já foi atualizado para usar String em vez de Enum
