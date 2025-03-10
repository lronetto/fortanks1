-- Tabela de modelos de checklist
CREATE TABLE IF NOT EXISTS checklist_modelos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    tipo_equipamento VARCHAR(50) NOT NULL,
    frequencia ENUM('diario', 'semanal', 'quinzenal', 'mensal', 'trimestral', 'semestral', 'anual') NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    criado_por INT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (criado_por) REFERENCES usuarios(id)
);

-- Tabela de itens de checklist (pontos de verificação)
CREATE TABLE IF NOT EXISTS checklist_itens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    modelo_id INT NOT NULL,
    texto VARCHAR(255) NOT NULL,
    tipo_resposta ENUM('sim_nao', 'valor_numerico', 'texto', 'selecao') NOT NULL,
    ordem INT NOT NULL,
    obrigatorio BOOLEAN DEFAULT TRUE,
    valores_possiveis TEXT, -- Para tipo_resposta = 'selecao', guarda as opções em formato JSON
    valor_minimo FLOAT NULL, -- Para tipo_resposta = 'valor_numerico'
    valor_maximo FLOAT NULL, -- Para tipo_resposta = 'valor_numerico'
    unidade VARCHAR(20) NULL, -- Para tipo_resposta = 'valor_numerico'
    imagem_referencia VARCHAR(255) NULL, -- Caminho para imagem de referência, se aplicável
    ativo BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (modelo_id) REFERENCES checklist_modelos(id) ON DELETE CASCADE
);

-- Tabela de checklists preenchidos
CREATE TABLE IF NOT EXISTS checklist_preenchidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    modelo_id INT NOT NULL,
    equipamento_id VARCHAR(50) NOT NULL, -- Identificador do equipamento (pode ser o número de série, código, etc.)
    equipamento_nome VARCHAR(100) NOT NULL,
    equipamento_local VARCHAR(100),
    responsavel_id INT NOT NULL,
    supervisor_id INT NULL, -- Supervisor que aprovou o checklist, se aplicável
    data_preenchimento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_aprovacao TIMESTAMP NULL,
    status ENUM('em_andamento', 'concluido', 'aprovado', 'rejeitado') NOT NULL DEFAULT 'em_andamento',
    observacoes TEXT,
    FOREIGN KEY (modelo_id) REFERENCES checklist_modelos(id),
    FOREIGN KEY (responsavel_id) REFERENCES usuarios(id),
    FOREIGN KEY (supervisor_id) REFERENCES usuarios(id)
);

-- Tabela de respostas de checklists
CREATE TABLE IF NOT EXISTS checklist_respostas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    checklist_id INT NOT NULL,
    item_id INT NOT NULL,
    resposta_texto TEXT NULL,
    resposta_numerica FLOAT NULL,
    resposta_booleana BOOLEAN NULL,
    observacao TEXT,
    conformidade ENUM('conforme', 'nao_conforme', 'nao_aplicavel') NOT NULL DEFAULT 'conforme',
    imagem_anexa VARCHAR(255) NULL, -- Caminho para imagem anexada, se aplicável
    data_resposta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (checklist_id) REFERENCES checklist_preenchidos(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES checklist_itens(id)
);

-- Tabela para registrar o histórico de alterações nos checklists
CREATE TABLE IF NOT EXISTS checklist_historico (
    id INT AUTO_INCREMENT PRIMARY KEY,
    checklist_id INT NOT NULL,
    usuario_id INT NOT NULL,
    acao VARCHAR(50) NOT NULL, -- 'criacao', 'edicao', 'aprovacao', 'rejeicao', etc.
    descricao TEXT NOT NULL,
    data_acao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (checklist_id) REFERENCES checklist_preenchidos(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- Índices para melhorar a performance
CREATE INDEX idx_checklist_equipamento ON checklist_preenchidos(equipamento_id);
CREATE INDEX idx_checklist_responsavel ON checklist_preenchidos(responsavel_id);
CREATE INDEX idx_checklist_status ON checklist_preenchidos(status);
CREATE INDEX idx_checklist_data ON checklist_preenchidos(data_preenchimento);
