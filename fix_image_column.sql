-- Script para alterar a coluna imagem para LONGTEXT
-- Execute este script diretamente no seu banco de dados MySQL

USE sfortanks;

-- Alterar a coluna imagem para LONGTEXT
ALTER TABLE ProdComp MODIFY COLUMN imagem LONGTEXT;

-- Verificar se a alteração foi aplicada
DESCRIBE ProdComp; 