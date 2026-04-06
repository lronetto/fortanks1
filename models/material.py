import json
from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship
from models.nota_fiscal import NotaFiscal, NotaFiscalItem

class Materiais(db.Model):

    """
    Modelo para representar materiais
    """
    __tablename__ = 'Materiais'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    codigo_erp = db.Column(db.String(50), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    plano_conta = db.Column(db.String(30), nullable=True)
    plano_conta_id = db.Column(db.Integer, db.ForeignKey('planos_conta.id'), nullable=True)
    plano_conta_obj = relationship('PlanoConta', back_populates='materiais',foreign_keys=[plano_conta_id])
    ncm = db.Column(db.String(15), nullable=True)
    mascara = db.Column(db.String(20), nullable=True)
    
    # Referência à tabela de unidades
    unidade_id = db.Column(db.Integer, db.ForeignKey('Unidades.id'), nullable=True)
    
    categoria = db.Column(db.String(50), nullable=True)  # Adicionando campo categoria
    formula_calculo = db.Column(db.String(500), nullable=True)  # Fórmula universal para cálculo de quantidade
    dados_adicionais = db.Column(db.Text, nullable=True)  # Dados adicionais em formato JSON
    criado_em = db.Column(db.DateTime, default=datetime.now)

    #unidade = db.relationship('Unidade', back_populates='materiais', foreign_keys=[unidade_id])
    # Relacionamento com itens de solicitação
    solicitacoes_itens = db.relationship('SolicitacoesItens', back_populates='material')
    # Renomeado para evitar conflito com o campo string 'unidade' e para maior clareza
    unidade_obj = db.relationship('Unidades', back_populates='materiais', foreign_keys=[unidade_id])
    
    # Relacionamento com grupos de materiais
    grupos = relationship('MateriaisGrupos', secondary='MateriaisGruposItens', back_populates='materiais')
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'unidade': self.unidade_obj.nome if self.unidade_obj else None,
            'unidade_id': self.unidade_id
        }
    
    def save(self):
        """
        Salva o material no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o material do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    @property
    def data_criacao(self):
        """
        Retorna a data de criação do material (para compatibilidade com código existente)
        """
        return self.criado_em

    @property
    def imagem_upload_id(self):
        """ID em Upload (tipo imagem material) gravado em dados_adicionais."""
        if not self.dados_adicionais or not str(self.dados_adicionais).strip():
            return None
        try:
            d = json.loads(self.dados_adicionais)
            if not isinstance(d, dict):
                return None
            v = d.get("imagem_upload_id")
            if v is None or v == "":
                return None
            return int(v)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    
    def __repr__(self):
        """
        Representação em string do material
        """
        codigo_display = self.codigo or "Sem código"
        return f'<Material {codigo_display} - {self.nome}>'
    
    def get_unidade_nome(self):
        """
        Retorna o nome da unidade do material
        """
        # Se tiver unidade_obj, usa o nome dela
        if hasattr(self, 'unidade_obj') and self.unidade_obj:
            return self.unidade_obj.nome
        # Senão, usa o campo string unidade
        return self.unidade
    
    def tem_conversoes(self):
        """
        Verifica se o material possui conversões de unidades
        """
        # Se não tiver unidade definida, não tem conversões
        if not self.unidade_id and not self.unidade:
            return False
            
        # Verifica se tem conversões específicas para este material
        return len(getattr(self, 'conversoes_unidade', [])) > 0
    def get_valor_unitario(self):
        """
        Retorna o valor unitário do material
        """
        item_nf = NotaFiscalItem.query.filter_by(material_id=self.id).join(NotaFiscal).order_by(NotaFiscal.data_emissao.desc()).first()
        if item_nf:
            return item_nf.valor_unitario/item_nf.fator_conversao_aplicado
        return 0
    
    def calcular_quantidade(self, quantidade_total, placas_normais, placas_fecho, quantidade_bainhas, altura_total=None, sistema=None):
        """
        Calcula a quantidade do material baseado na fórmula universal de cálculo
        A fórmula é universal (cadastrada no material), mas usa os dados específicos do tanque
        
        Variáveis disponíveis na fórmula:
        - quantidade_total: quantidade de tanques
        - placas_normais: quantidade de placas normais
        - placas_fecho: quantidade de placas de fecho
        - quantidade_bainhas: quantidade de bainhas
        - altura_total: altura total do tanque
        - sistema: sistema do tanque (SC-10, SC-14, SR-06)
        """
        if not self.formula_calculo:
            return 1.0
        
        try:
            # Criar um contexto seguro para eval
            contexto = {
                'quantidade_total': float(quantidade_total or 1),
                'placas_normais': float(placas_normais or 0),
                'placas_fecho': float(placas_fecho or 0),
                'quantidade_bainhas': float(quantidade_bainhas or 0),
                'altura_total': float(altura_total or 0),
                'sistema': sistema or '',
            }
            
            # Substituir variáveis na fórmula por valores seguros
            formula = self.formula_calculo.strip()
            
            # Avaliar a fórmula de forma segura
            resultado = eval(formula, {"__builtins__": {}}, contexto)
            
            return float(resultado) if resultado else 1.0
        except Exception as e:
            # Em caso de erro, retornar 1.0 como padrão
            print(f"Erro ao calcular fórmula para material {self.id}: {str(e)}")
            return 1.0

class MateriaisGrupos(db.Model):
    """
    Modelo para representar grupos de materiais para inventário
    """
    __tablename__ = 'MateriaisGrupos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text, nullable=True)
    codigo = db.Column(db.String(20), nullable=True, unique=True)
    ativo = db.Column(db.Boolean, default=True)
    cor = db.Column(db.String(7), nullable=True)  # Código hexadecimal da cor
    icone = db.Column(db.String(50), nullable=True)  # Classe do ícone (ex: fas fa-boxes)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    # Relacionamentos
    criado_por = relationship('Usuario', foreign_keys=[criado_por_id])

    materiais = relationship('Materiais', secondary='MateriaisGruposItens', back_populates='grupos')
    
    def __repr__(self):
        return f'<MaterialGrupo {self.codigo or self.id} - {self.nome}>'
    
    def to_dict(self):
        """
        Converte o grupo para dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'codigo': self.codigo,
            'ativo': self.ativo,
            'cor': self.cor,
            'icone': self.icone,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None,
            'criado_por': self.criado_por.nome if self.criado_por else None,
            'total_materiais': len(self.materiais) if self.materiais else 0
        }
    
    def save(self):
        """
        Salva o grupo no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o grupo do banco de dados
        """
        # Remove as associações com materiais primeiro usando SQLAlchemy ORM
        self.materiais.clear()
        db.session.delete(self)
        db.session.commit()
    
    @classmethod
    def get_ativos(cls):
        """
        Retorna todos os grupos ativos
        """
        return cls.query.filter_by(ativo=True).order_by(cls.nome).all()
    
    @classmethod
    def get_por_codigo(cls, codigo):
        """
        Busca grupo por código
        """
        return cls.query.filter_by(codigo=codigo, ativo=True).first()
    
    def adicionar_material(self, material):
        """
        Adiciona um material ao grupo
        Verifica se já existe antes de adicionar para evitar duplicatas
        """
        # Verificar se o material já está no grupo usando SQLAlchemy ORM
        if material in self.materiais:
            # Material já está no grupo, não fazer nada
            return False
        
        # Adicionar o material
        self.materiais.append(material)
        db.session.commit()
        return True
    
    def remover_material(self, material):
        """
        Remove um material do grupo
        """
        if material in self.materiais:
            self.materiais.remove(material)
            db.session.commit()
    
    def get_materiais_ativos(self):
        """
        Retorna apenas os materiais ativos do grupo
        """
        return [material for material in self.materiais if material.ativo]
    
    @property
    def total_materiais(self):
        """
        Retorna o total de materiais no grupo
        """
        return len(self.materiais) if self.materiais else 0
    
    @property
    def total_materiais_ativos(self):
        """
        Retorna o total de materiais ativos no grupo
        """
        return len(self.get_materiais_ativos())


# Tabela de associação entre materiais e grupos
# Nota: O nome da tabela no banco é 'materiais_grupos' (conforme migration e código SQL)
materiais_grupos = db.Table('MateriaisGruposItens',
    db.Column('id', db.Integer, primary_key=True, autoincrement=True),
    db.Column('material_id', db.Integer, db.ForeignKey('Materiais.id'), primary_key=False),
    db.Column('grupo_id', db.Integer, db.ForeignKey('MateriaisGrupos.id'), primary_key=False),
    db.Column('data_associacao', db.DateTime, default=datetime.now),
    db.PrimaryKeyConstraint('id'),
)
