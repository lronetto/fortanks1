from datetime import datetime
import json

from .database import db
UNIDADES_IGUAIS = [
    ['UN','UND','UNIDADE','UNIDADES','UNID','UNID.','PAR','PR','PC','PA','UNIDA'],
    ['KG','KILOS','Kg'],
    ['GALAO','GALAO','Galao'],
    ['PCT','PCT','Pct'],
    ['L','LITROS','Litro'],
    ['M²','M²','M²'],
    ['M³','M³','M³'],
    ['TON','TON','Ton','TL','TO','TN','T'],
    ['M','Metro','Mt','MTR'],
    ['G','G','G'],
    ['ML','ML','Ml'],
    ['CM','CM','Cm'],
    ['MIL','MIL','Mil','MI'],
]
def comparar_unidades(unidade_entrada, unidade_saida):
    unidade_entrada = unidade_entrada.upper()
    unidade_saida = unidade_saida.upper()
    if unidade_entrada == unidade_saida:
        return True
    else:       
        for unidade in UNIDADES_IGUAIS:
            if unidade_entrada in unidade and unidade_saida in unidade:
                return True
            else:
                return False
    return False
def normalizar_unidade(unidade):
    unidade_normalizada = unidade.upper()
    for lista_unidades in UNIDADES_IGUAIS:
        if unidade_normalizada in lista_unidades:
            return lista_unidades[0]  # Retorna a primeira unidade da lista
    return unidade_normalizada
def get_conversao_unidade(material_id=None,unidade_entrada=None, unidade_saida=None):
    # Import local para evitar import circular
    from models.material import Materiais
    # UnidadesConversao está definido neste mesmo arquivo, não precisa importar
    
    if unidade_entrada is not None:
        unidade_entrada = normalizar_unidade(unidade_entrada)
    if unidade_saida is not None:
        unidade_saida = normalizar_unidade(unidade_saida)
    if unidade_entrada is None and unidade_saida is None:
        return False
    if unidade_entrada == unidade_saida:
        return 1.0
    unidade = unidade_entrada or unidade_saida
    if material_id is not None:
        material = Materiais.query.filter_by(id=material_id).first()
        if not material:
            return False
        if material.dados_adicionais:
           
            dados_adicionais = json.loads(material.dados_adicionais)
            unidade_material = material.unidade_obj.nome if material.unidade_obj else None
            if unidade_material == unidade_entrada:
                return 1.0
            if dados_adicionais and dados_adicionais.get('conversao'):
                for conversao in dados_adicionais.get('conversao'):
                    conversor = UnidadesConversao.query.filter_by(id=conversao).first()
                    print(f"material.nome: {material.nome}, conversao: {conversao}, conversor.unidade_saida: {conversor.unidade_saida}, conversor.unidade_entrada: {conversor.unidade_entrada}, unidade_saida: {unidade_saida}, unidade_entrada: {unidade_entrada},conversor.fator: {conversor.fator}")
                    if conversor.unidade_saida == unidade_saida and unidade_saida is not None:
                        return conversor.fator
                    elif conversor.unidade_entrada == unidade_entrada and unidade_entrada is not None:
                        return 1.0 / conversor.fator
        if unidade_saida is not None:
            if normalizar_unidade(unidade_saida) == material.unidade_obj.nome:
                return 1.0

            conversao = UnidadesConversao.query.filter_by(unidade_entrada=material.unidade_obj.nome, unidade_saida=unidade_saida).first()
            if conversao:
                return conversao.fator
            else:
                return False
        if unidade_entrada is not None:
            if normalizar_unidade(unidade_entrada) == material.unidade_obj.nome:
                return 1.0
            conversao = UnidadesConversao.query.filter_by(unidade_entrada=unidade_entrada, unidade_saida=material.unidade_obj.nome).first()
            if conversao:
                return conversao.fator
            else:
                return False
        return False
    else:
        conversao = UnidadesConversao.query.filter_by(unidade_entrada=unidade_entrada, unidade_saida=unidade_saida).first()
        if conversao:
            return conversao.fator
        else:
            conversao = UnidadesConversao.query.filter_by(unidade_entrada=unidade_saida, unidade_saida=unidade_entrada).first()
            if conversao:
                return 1.0 / conversao.fator
        return False


class Unidades(db.Model):
    """Modelo para armazenar unidades de medida."""
    __tablename__ = 'Unidades'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(10), nullable=False, unique=True)
    descricao = db.Column(db.String(100), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    padrao = db.Column(db.Boolean, default=False)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    materiais = db.relationship('Materiais', back_populates='unidade_obj', lazy=True)
    conversoes_origem = db.relationship(
        'UnidadesConversao', 
        foreign_keys='UnidadesConversao.unidade_origem_id',
        back_populates='unidade_origem',
        lazy=True
    )
    conversoes_destino = db.relationship(
        'UnidadesConversao', 
        foreign_keys='UnidadesConversao.unidade_destino_id',
        back_populates='unidade_destino',
        lazy=True
    )
    nf_itens = db.relationship('NotaFiscalItem', back_populates='unidade_rel', lazy=True)
    
    def __repr__(self):
        return f"<Unidade {self.nome}>"
    
    @classmethod
    def obter_padrao(cls):
        """Retorna a unidade padrão do sistema"""
        return cls.query.filter_by(padrao=True).first()
    
    @classmethod
    def obter_por_nome(cls, nome):
        """Retorna uma unidade pelo seu nome"""
        return cls.query.filter(cls.nome.ilike(nome)).first()
    
    @classmethod
    def criar_unidades_padrao(cls):
        """Cria as unidades padrão do sistema se não existirem"""
        unidades_padrao = [
            {'nome': 'UN', 'descricao': 'Unidade', 'padrao': True},
            {'nome': 'KG', 'descricao': 'Quilograma'},
            {'nome': 'G', 'descricao': 'Grama'},
            {'nome': 'L', 'descricao': 'Litro'},
            {'nome': 'ML', 'descricao': 'Mililitro'},
            {'nome': 'M', 'descricao': 'Metro'},
            {'nome': 'CM', 'descricao': 'Centímetro'},
            {'nome': 'M²', 'descricao': 'Metro quadrado'},
            {'nome': 'M³', 'descricao': 'Metro cúbico'},
            {'nome': 'PCT', 'descricao': 'Pacote'},
            {'nome': 'CX', 'descricao': 'Caixa'},
            {'nome': 'PAR', 'descricao': 'Par'},
            {'nome': 'TON', 'descricao': 'Tonelada'},
            {'nome': 'GALÃO', 'descricao': 'Galão'},
        ]
        
        for unidade_data in unidades_padrao:
            # Verifica se a unidade já existe
            unidade = cls.query.filter(cls.nome.ilike(unidade_data['nome'])).first()
            if not unidade:
                # Cria a unidade se não existir
                unidade = cls(**unidade_data)
                db.session.add(unidade)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao criar unidades padrão: {str(e)}") 

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao
        }
class UnidadesConversao(db.Model):
    """Modelo para armazenar as conversões de unidades."""
    __tablename__ = 'UnidadesConversao'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    
    # Unidades como strings (para compatibilidade)
    unidade_entrada = db.Column(db.String(20), nullable=False)
    unidade_saida = db.Column(db.String(20), nullable=False)
    
    # Relacionamentos com o modelo Unidade
    unidade_origem_id = db.Column(db.Integer, db.ForeignKey('Unidades.id'), nullable=True)
    unidade_destino_id = db.Column(db.Integer, db.ForeignKey('Unidades.id'), nullable=True)
    
    # Relacionamentos bidirecionais com Unidade
    unidade_origem = db.relationship('Unidades', foreign_keys=[unidade_origem_id], back_populates='conversoes_origem', lazy=True)
    unidade_destino = db.relationship('Unidades', foreign_keys=[unidade_destino_id], back_populates='conversoes_destino', lazy=True)
    
    # Material associado à conversão (opcional)
    material_id = db.Column(db.Integer, db.ForeignKey('Materiais.id'), nullable=True)
    material = db.relationship('Materiais', backref='conversoes_unidade', lazy=True)
    
    # Fator de conversão
    fator = db.Column(db.Float, nullable=False)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Conjunto de unidades padrão para compatibilidade
    unidades_padrao = {'UN','KG','GALAO','PCT','L','M²','M³','TON','M','G','ML','CM','CX','PAR'}
    
    def __repr__(self):
        return f"<ConversaoUnidade {self.unidade_entrada} para {self.unidade_saida}>"
    
    @property
    def converter(self,quantidade,unidade_entrada,unidade_saida):
        if unidade_entrada == unidade_saida:
            return quantidade
        else:
            existe = self.query.filter_by(unidade_entrada=unidade_entrada, unidade_saida=unidade_saida).first()
            if existe:
                return quantidade * existe.fator
            else:
                existe = self.query.filter_by(unidade_entrada=unidade_saida, unidade_saida=unidade_entrada).first()
                if existe:
                    return quantidade / existe.fator
                else:
                    return None
        
    @classmethod
    def obter_por_unidades(cls, unidade_entrada, unidade_saida, material_id=None):
        """Busca uma conversão com base nas unidades de entrada e saída e material opcional"""
        query = cls.query.filter_by(unidade_entrada=unidade_entrada, unidade_saida=unidade_saida)
        
        if material_id:
            # Primeiro tenta encontrar uma conversão específica para o material
            conversao = query.filter_by(material_id=material_id).first()
            if conversao:
                return conversao
                
        # Se não encontrar específica ou não tiver material, busca genérica
        return query.filter_by(material_id=None).first()
    
    @classmethod
    def obter_por_ids(cls, unidade_origem_id, unidade_destino_id, material_id=None):
        """Busca uma conversão com base nos IDs das unidades e material opcional"""
        query = cls.query.filter_by(unidade_origem_id=unidade_origem_id, 
                                    unidade_destino_id=unidade_destino_id)
        
        if material_id:
            # Primeiro tenta encontrar uma conversão específica para o material
            conversao = query.filter_by(material_id=material_id).first()
            if conversao:
                return conversao
                
        # Se não encontrar específica ou não tiver material, busca genérica
        return query.filter_by(material_id=None).first()
    
    @classmethod
    def listar_para_material(cls, material_id):
        """Lista todas as conversões disponíveis para um material"""
        # Busca conversões específicas para o material
        conversoes_especificas = cls.query.filter_by(material_id=material_id).all()
        
        # Busca conversões genéricas (sem material associado)
        conversoes_genericas = cls.query.filter_by(material_id=None).all()
        
        # Combina os resultados (conversões específicas têm prioridade)
        conversoes = {}
        
        # Adiciona as conversões genéricas
        for conv in conversoes_genericas:
            chave = (conv.unidade_entrada, conv.unidade_saida)
            conversoes[chave] = conv
            
        # Adiciona as conversões específicas (substituindo as genéricas se existirem)
        for conv in conversoes_especificas:
            chave = (conv.unidade_entrada, conv.unidade_saida)
            conversoes[chave] = conv
            
        return list(conversoes.values())

    @classmethod
    def obter_fator_conversao(cls, unidade_origem_id: int, unidade_destino_id: int, material_id: int = None) -> float | None:
        """ Tenta obter um fator de conversão entre duas unidades (por ID), considerando material específico e conversões inversas.
            Retorna o fator para multiplicar pela quantidade na unidade_origem para obter a quantidade na unidade_destino.
        """
        if unidade_origem_id == unidade_destino_id:
            return 1.0

        # 1. Tenta conversão direta específica para o material
        conversao = cls.query.filter_by(
            unidade_origem_id=unidade_origem_id,
            unidade_destino_id=unidade_destino_id,
            material_id=material_id
        ).first()
        if conversao:
            return conversao.fator

        # 2. Tenta conversão direta genérica (sem material_id)
        conversao = cls.query.filter_by(
            unidade_origem_id=unidade_origem_id,
            unidade_destino_id=unidade_destino_id,
            material_id=None
        ).first()
        if conversao:
            return conversao.fator

        # 3. Tenta conversão inversa específica para o material
        conversao_inversa = cls.query.filter_by(
            unidade_origem_id=unidade_destino_id, # Invertido
            unidade_destino_id=unidade_origem_id, # Invertido
            material_id=material_id
        ).first()
        if conversao_inversa and conversao_inversa.fator != 0:
            return 1.0 / conversao_inversa.fator

        # 4. Tenta conversão inversa genérica
        conversao_inversa = cls.query.filter_by(
            unidade_origem_id=unidade_destino_id, # Invertido
            unidade_destino_id=unidade_origem_id, # Invertido
            material_id=None
        ).first()
        if conversao_inversa and conversao_inversa.fator != 0:
            return 1.0 / conversao_inversa.fator
            
        return None # Nenhuma conversão encontrada 