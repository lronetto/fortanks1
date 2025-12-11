from datetime import datetime
from .database import db
UNIDADES_IGUAIS = [
    ['UN','UND','UNIDADE','UNIDADES','UNID','UNID.','PAR','PR','PC','PA'],
    ['KG','KILOS','Kg'],
    ['GALAO','GALAO','Galao'],
    ['PCT','PCT','Pct'],
    ['L','LITROS','Litro'],
    ['M²','M²','M²'],
    ['M³','M³','M³'],
    ['TON','TON','Ton','TL','TO','TN'],
    ['M','Metro','Mt','MTR'],
    ['G','G','G'],
    ['ML','ML','Ml'],
    ['CM','CM','Cm'],
    ['MIL','MIL','Mil'],
    ['MIL','MIL','Mil'],
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
def get_conversao_unidade(unidade_entrada, unidade_saida):
    unidade_entrada = normalizar_unidade(unidade_entrada)
    unidade_saida = normalizar_unidade(unidade_saida)
    if unidade_entrada == unidade_saida:
        return 1.0
    conversao = ConversaoUnidade.query.filter_by(unidade_entrada=unidade_entrada, unidade_saida=unidade_saida).first()
    if conversao:
        return conversao.fator
    else:
        conversao = ConversaoUnidade.query.filter_by(unidade_entrada=unidade_saida, unidade_saida=unidade_entrada).first()
        if conversao:
            return 1.0 / conversao.fator
                        
class ConversaoUnidade(db.Model):
    """Modelo para armazenar as conversões de unidades."""
    __tablename__ = 'conversoes_unidades'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    
    # Unidades como strings (para compatibilidade)
    unidade_entrada = db.Column(db.String(20), nullable=False)
    unidade_saida = db.Column(db.String(20), nullable=False)
    
    # Relacionamentos com o modelo Unidade
    unidade_origem_id = db.Column(db.Integer, db.ForeignKey('unidades.id'), nullable=True)
    unidade_destino_id = db.Column(db.Integer, db.ForeignKey('unidades.id'), nullable=True)
    
    # Material associado à conversão (opcional)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=True)
    material = db.relationship('Material', backref='conversoes_unidade', lazy=True)
    
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