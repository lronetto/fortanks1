"""Modelo principal de tanques de projetos."""

from datetime import datetime

from sqlalchemy import String, cast, func

from models.database import db


class Tanques(db.Model):
    """
    Modelo para representar tanques de projetos
    """
    __tablename__ = 'Tanques'

    id = db.Column(db.Integer, primary_key=True)
    un = db.Column(db.String(50), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    sistema = db.Column(db.String(10), nullable=False)  # SC-10, SC-14, SR-06
    dimensoes = db.Column(db.String(100), nullable=False)  # Exibição formatada das dimensões

    # Dimensões numéricas para cálculos
    diametro = db.Column(db.Float, nullable=True)  # Para tanques circulares (SC)
    comprimento = db.Column(db.Float, nullable=True)  # Para tanques retangulares (SR)
    largura = db.Column(db.Float, nullable=True)  # Para tanques retangulares (SR)

    altura_total = db.Column(db.Float, nullable=False)
    altura_util = db.Column(db.Float, nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    cobertura = db.Column(db.Boolean, default=False)
    ncabospn = db.Column(db.Integer, nullable=False, default=0)
    ncabospf = db.Column(db.Integer, nullable=False, default=0)
    quantidade_bainhas = db.Column(db.Integer, nullable=True, default=0)
    # Quantidades de placas
    placas_normais = db.Column(db.Integer, default=0)
    placas_fecho = db.Column(db.Integer, default=0)
    valorUnitario = db.Column(db.Float, nullable=True, default=0)
    dados_adicionais = db.Column(db.Text, nullable=True)

    # Chave estrangeira para contrato
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)

    item_nf = db.Column(db.Integer, nullable=True)

    # Datas de controle
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamentos
    contrato = db.relationship('Contrato', back_populates='tanques', foreign_keys=[contrato_id])
    grupos = db.relationship('TanquesGrupos', secondary='TanquesGruposItens', back_populates='tanques')

    @property
    def tipo_tanque(self):
        """Retorna o tipo do tanque (Circular ou Retangular) baseado no sistema"""
        if self.sistema.startswith('SC'):
            return 'Circular'
        elif self.sistema.startswith('SR'):
            return 'Retangular'
        return 'Desconhecido'

    @property
    def possui_cobertura(self):
        """Retorna texto formatado indicando se possui cobertura"""
        return "Sim" if self.cobertura else "Não"

    @property
    def area_base(self):
        """Calcula a área da base do tanque em m²"""
        if self.tipo_tanque == 'Circular' and self.diametro:
            raio = self.diametro / 2
            return 3.14159 * (raio ** 2)
        elif self.tipo_tanque == 'Retangular' and self.comprimento and self.largura:
            return self.comprimento * self.largura
        return None

    @property
    def volume_util(self):
        """Calcula o volume útil do tanque em m³"""
        area = self.area_base
        if area and self.altura_util:
            return area * self.altura_util
        return None

    @property
    def volume_total(self):
        """Calcula o volume total do tanque em m³"""
        area = self.area_base
        if area and self.altura_total:
            return area * self.altura_total
        return None

    @staticmethod
    def gerar_un():
        """
        Gera um código UN único baseado na data e hora atual
        """
        return f"T{datetime.now().strftime('%Y%m%d%H%M%S')}"

    @staticmethod
    def sql_codigo_nf_igual_item_nf_colunas(codigo_item_col, item_nf_col):
        """
        Uma NF pode ter vários itens (cadastros/tanques/códigos distintos). Esta expressão
        associa cada linha de item apenas ao tanque cujo item_nf coincide com o
        código do item, comparando como texto (evita coerção numérica no SGBD).
        """
        return func.trim(codigo_item_col) == cast(item_nf_col, String)

    @staticmethod
    def sql_codigo_nf_igual_item_nf_valor(codigo_item_col, item_nf_int):
        """Filtro: coluna codigo do item da NF igual ao item_nf (int) deste tanque."""
        return func.trim(codigo_item_col) == str(item_nf_int).strip()

    def before_save(self):
        """
        Verifica e configura campos antes de salvar
        """
        # Garantir que o campo UN sempre tenha um valor
        if not self.un:
            self.un = self.gerar_un()

    def to_dict(self):
        """
        Retorna um dicionário com os campos do tanque
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'un': self.un,
            'sistema': self.sistema,
            'dimensoes': self.dimensoes,
            'diametro': self.diametro,
            'comprimento': self.comprimento,
            'largura': self.largura,
            'altura_total': self.altura_total,
            'altura_util': self.altura_util,
            'quantidade': self.quantidade,
            'cobertura': self.cobertura,
            'ncabospn': self.ncabospn,
            'ncabospf': self.ncabospf,
            'quantidade_bainhas': self.quantidade_bainhas,
            'placas_normais': self.placas_normais,
            'placas_fecho': self.placas_fecho,
            'contrato_id': self.contrato_id,
            'item_nf': self.item_nf,
            'data_cadastro': self.data_cadastro,
            'ultima_atualizacao': self.ultima_atualizacao
        }

    def save(self):
        """
        Salva o tanque no banco de dados
        """
        self.before_save()  # Verifica e configura campos antes de salvar
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """
        Remove o tanque do banco de dados
        """
        db.session.delete(self)
        db.session.commit()

    def __repr__(self):
        """
        Representação em string do tanque
        """
        return f'<Tanque {self.id} - {self.nome} ({self.sistema})>'

    def atualizar_dimensoes_numericas(self):
        """
        Extrai valores numéricos das dimensões formatadas e atualiza os campos correspondentes
        """
        from ..services.dimensoes_e_estatisticas import atualizar_dimensoes_numericas
        return atualizar_dimensoes_numericas(self)

    def get_pecas_id_concretadas(self):
        """
        Retorna as peças concretadas do tanque
        """
        from ..services.dimensoes_e_estatisticas import obter_pecas_ids_concretadas_via_concretagens
        return obter_pecas_ids_concretadas_via_concretagens(self)

    def get_pecas_concretadas(self):
        """
        Retorna o total de peças concretadas do tanque
        """
        from ..services.dimensoes_e_estatisticas import listar_ids_pecas_com_data_concretagem
        return listar_ids_pecas_com_data_concretagem(self)

    def get_concretadas(self):
        """
        Retorna o total de concretagens do tanque
        """
        from ..services.dimensoes_e_estatisticas import contar_concretadas
        return contar_concretadas(self)

    def get_statistics(self, data_ate=None):
        """
        Retorna as estatísticas do tanque até a data informada (inclusive).
        data_ate: date ou None (usa data atual).
        """
        from ..services.dimensoes_e_estatisticas import calcular_estatisticas_tanque
        return calcular_estatisticas_tanque(self, data_ate)
