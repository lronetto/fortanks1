"""
Script SQL para criar a tabela de unidades e adicionar campos relacionados
Use este script com cuidado, ele modifica a estrutura do banco de dados.
"""

criar_tabela_unidades = """
-- Criar tabela de unidades
CREATE TABLE IF NOT EXISTS unidades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(10) NOT NULL UNIQUE,
    descricao VARCHAR(100),
    ativo BOOLEAN DEFAULT TRUE,
    padrao BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Adicionar campos de unidades aos materiais
ALTER TABLE materiais 
ADD COLUMN IF NOT EXISTS unidade_id INT,
ADD CONSTRAINT fk_material_unidade FOREIGN KEY (unidade_id) REFERENCES unidades(id);

-- Adicionar campos de unidades às conversões
ALTER TABLE conversoes_unidades 
ADD COLUMN IF NOT EXISTS unidade_origem_id INT,
ADD COLUMN IF NOT EXISTS unidade_destino_id INT,
ADD COLUMN IF NOT EXISTS material_id INT,
ADD CONSTRAINT fk_conversao_unidade_origem FOREIGN KEY (unidade_origem_id) REFERENCES unidades(id),
ADD CONSTRAINT fk_conversao_unidade_destino FOREIGN KEY (unidade_destino_id) REFERENCES unidades(id),
ADD CONSTRAINT fk_conversao_material FOREIGN KEY (material_id) REFERENCES materiais(id);

-- Adicionar campos de unidades aos itens de nota fiscal
ALTER TABLE nf_itens
ADD COLUMN IF NOT EXISTS unidade_id INT,
ADD CONSTRAINT fk_nf_item_unidade FOREIGN KEY (unidade_id) REFERENCES unidades(id);

-- Inserir unidades padrão (básicas)
INSERT INTO unidades (nome, descricao, ativo, padrao) VALUES 
('UN', 'Unidade', TRUE, TRUE),
('KG', 'Quilograma', TRUE, FALSE),
('G', 'Grama', TRUE, FALSE),
('L', 'Litro', TRUE, FALSE),
('ML', 'Mililitro', TRUE, FALSE),
('M', 'Metro', TRUE, FALSE),
('CM', 'Centímetro', TRUE, FALSE),
('M²', 'Metro quadrado', TRUE, FALSE),
('M³', 'Metro cúbico', TRUE, FALSE),
('PCT', 'Pacote', TRUE, FALSE),
('CX', 'Caixa', TRUE, FALSE),
('PAR', 'Par', TRUE, FALSE),
('TON', 'Tonelada', TRUE, FALSE),
('GALÃO', 'Galão', TRUE, FALSE)
ON DUPLICATE KEY UPDATE 
    descricao = VALUES(descricao),
    ativo = VALUES(ativo);

-- Migrar unidades existentes dos materiais
UPDATE materiais m
JOIN unidades u ON UPPER(TRIM(m.unidade)) = UPPER(TRIM(u.nome))
SET m.unidade_id = u.id
WHERE m.unidade IS NOT NULL AND m.unidade != '';

-- Migrar unidades existentes das conversões
UPDATE conversoes_unidades c
JOIN unidades uo ON UPPER(TRIM(c.unidade_entrada)) = UPPER(TRIM(uo.nome))
JOIN unidades ud ON UPPER(TRIM(c.unidade_saida)) = UPPER(TRIM(ud.nome))
SET c.unidade_origem_id = uo.id, c.unidade_destino_id = ud.id
WHERE c.unidade_entrada IS NOT NULL AND c.unidade_entrada != ''
  AND c.unidade_saida IS NOT NULL AND c.unidade_saida != '';
"""

# Para PostgreSQL
criar_tabela_unidades_pg = """
-- Criar tabela de unidades
CREATE TABLE IF NOT EXISTS unidades (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(10) NOT NULL UNIQUE,
    descricao VARCHAR(100),
    ativo BOOLEAN DEFAULT TRUE,
    padrao BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Adicionar campos de unidades aos materiais
ALTER TABLE materiais 
ADD COLUMN IF NOT EXISTS unidade_id INTEGER REFERENCES unidades(id);

-- Adicionar campos de unidades às conversões
ALTER TABLE conversoes_unidades 
ADD COLUMN IF NOT EXISTS unidade_origem_id INTEGER REFERENCES unidades(id),
ADD COLUMN IF NOT EXISTS unidade_destino_id INTEGER REFERENCES unidades(id),
ADD COLUMN IF NOT EXISTS material_id INTEGER REFERENCES materiais(id);

-- Adicionar campos de unidades aos itens de nota fiscal
ALTER TABLE nf_itens
ADD COLUMN IF NOT EXISTS unidade_id INTEGER REFERENCES unidades(id);

-- Criar a trigger para atualizar o timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_unidade_timestamp ON unidades;
CREATE TRIGGER update_unidade_timestamp
BEFORE UPDATE ON unidades
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Inserir unidades padrão (básicas)
DO $$
BEGIN 
    INSERT INTO unidades (nome, descricao, ativo, padrao) VALUES 
    ('UN', 'Unidade', TRUE, TRUE),
    ('KG', 'Quilograma', TRUE, FALSE),
    ('G', 'Grama', TRUE, FALSE),
    ('L', 'Litro', TRUE, FALSE),
    ('ML', 'Mililitro', TRUE, FALSE),
    ('M', 'Metro', TRUE, FALSE),
    ('CM', 'Centímetro', TRUE, FALSE),
    ('M²', 'Metro quadrado', TRUE, FALSE),
    ('M³', 'Metro cúbico', TRUE, FALSE),
    ('PCT', 'Pacote', TRUE, FALSE),
    ('CX', 'Caixa', TRUE, FALSE),
    ('PAR', 'Par', TRUE, FALSE),
    ('TON', 'Tonelada', TRUE, FALSE),
    ('GALÃO', 'Galão', TRUE, FALSE)
    ON CONFLICT (nome) DO UPDATE 
    SET descricao = EXCLUDED.descricao,
        ativo = EXCLUDED.ativo;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Erro ao inserir unidades: %', SQLERRM;
END $$;

-- Migrar unidades existentes dos materiais
UPDATE materiais m
SET unidade_id = u.id
FROM unidades u
WHERE UPPER(TRIM(m.unidade)) = UPPER(TRIM(u.nome))
AND m.unidade IS NOT NULL AND m.unidade != '';

-- Migrar unidades existentes das conversões
UPDATE conversoes_unidades c
SET unidade_origem_id = uo.id, unidade_destino_id = ud.id
FROM unidades uo, unidades ud
WHERE UPPER(TRIM(c.unidade_entrada)) = UPPER(TRIM(uo.nome))
AND UPPER(TRIM(c.unidade_saida)) = UPPER(TRIM(ud.nome))
AND c.unidade_entrada IS NOT NULL AND c.unidade_entrada != ''
AND c.unidade_saida IS NOT NULL AND c.unidade_saida != '';
""" 