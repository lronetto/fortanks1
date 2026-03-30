from datetime import datetime, date
import json
from models.concreto import ConcretoConcretagens, qualidade_peca_remover_data_producao_de_dados_adicionais
from models.database import db
from sqlalchemy.orm import relationship
from sqlalchemy import func, distinct, cast, String

from models.nota_fiscal import NotaFiscalItem, NotaFiscal
from models.nota_fiscal import CNPJS_MATRIZ
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
    contrato = db.relationship('Contrato',back_populates='tanques',foreign_keys=[contrato_id])
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
        Uma NF pode ter vários itens (tanques/códigos distintos). Esta expressão
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
        try:
            # Para tanques circulares, extrair o diâmetro
            if self.tipo_tanque == 'Circular':
                # Remover possíveis unidades e converter para float
                valor_str = self.dimensoes.replace('m', '').replace('M', '').strip()
                # Substituir vírgula por ponto para conversão
                valor_str = valor_str.replace(',', '.')
                self.diametro = float(valor_str)
                self.comprimento = None
                self.largura = None
            
            # Para tanques retangulares, extrair comprimento e largura
            elif self.tipo_tanque == 'Retangular':
                # Espera-se formato como "4,0m x 5,0m" ou similar
                partes = self.dimensoes.lower().replace('m', '').split('x')
                if len(partes) >= 2:
                    # Substituir vírgula por ponto para conversão
                    comp_str = partes[0].strip().replace(',', '.')
                    larg_str = partes[1].strip().replace(',', '.')
                    self.comprimento = float(comp_str)
                    self.largura = float(larg_str)
                    self.diametro = None
            
            return True
        except (ValueError, IndexError) as e:
            print(f"Erro ao extrair dimensões numéricas para o tanque {self.id}: {str(e)}")
            return False 
    def get_pecas_id_concretadas(self):
        """
        Retorna as peças concretadas do tanque
        """
        concretagens = ConcretoConcretagens.query.all()
        pecas_ids = []
        if concretagens:
            for concretagem in concretagens:
                pecas = concretagem.get_pecas()
                if pecas:
                    for peca in pecas:
                        if peca['tanque_id'] == self.id:
                            peca = TanquesPecas.query.filter(TanquesPecas.tanque_id == self.id, TanquesPecas.nome == peca['nome']).first()
                            if peca and peca.id not in pecas_ids:
                                pecas_ids.append(peca.id)
        return pecas_ids
    def get_pecas_concretadas(self):
        """
        Retorna o total de peças concretadas do tanque
        """
        pecas_ids = []
        for peca in self.TanquesPecas:
            if peca.data_concretagem:
                pecas_ids.append(peca.id)
        return pecas_ids
    def get_concretadas(self):
        """
        Retorna o total de concretagens do tanque
        """
        return len(self.get_pecas_concretadas())
    def _parse_data_ate(self, value):
        """Converte valor para date para comparação; retorna None se inválido."""
        if value is None:
            return None
        if isinstance(value, date):
            return value if not isinstance(value, datetime) else value.date()
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and value.strip() not in ('', 'null'):
            s = value.strip()
            s_date = s[:10] if len(s) >= 10 else s
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    d = datetime.strptime(s_date, fmt)
                    return d.date()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(s.replace('Z', '+00:00')).date()
            except (ValueError, AttributeError):
                pass
        return None

    def get_statistics(self, data_ate=None):
        """
        Retorna as estatísticas do tanque até a data informada (inclusive).
        data_ate: date ou None (usa data atual).
        """
        data_ate = data_ate or date.today()
        if isinstance(data_ate, datetime):
            data_ate = data_ate.date()

        pecas_acabadas = 0
        pecas_transportadas = 0
        pecas_em_estoque = 0
        pecas_prontas_transportar = 0
        nfs_emitidas_total = 0
        pecas_nfs_quantidade = 0
        pecas_concretadas = 0
        pecas_perca = 0  # peças marcadas como perda no qualidade (ex: "perca": true)
        for peca in self.TanquesPecas:
            if peca.qualidade:
                try:
                    qualidade_dict = json.loads(peca.qualidade) if isinstance(peca.qualidade, str) else peca.qualidade
                    # Peças marcadas como perca no qualidade
                    if qualidade_dict.get('perca') is True:
                        pecas_perca += 1
                    # Verificar acabamento (considerar apenas se data <= data_ate)
                    if 'acabamento' in qualidade_dict and qualidade_dict['acabamento']:
                        acabamento = qualidade_dict['acabamento']
                        data_acabamento = None
                        if isinstance(acabamento, dict):
                            val = acabamento.get('data')
                            if val is not None and str(val).strip() not in ('', 'null'):
                                data_acabamento = self._parse_data_ate(val)
                            if data_acabamento is not None and data_acabamento <= data_ate:
                                pecas_acabadas += 1
                        elif isinstance(acabamento, str):
                            if acabamento.strip() not in ('', 'null'):
                                pecas_acabadas += 1  # sem data, considera
                        else:
                            if bool(acabamento):
                                pecas_acabadas += 1

                    # Verificar transporte (considerar apenas se data_transporte <= data_ate)
                    if 'transporte' in qualidade_dict and qualidade_dict['transporte']:
                        transporte = qualidade_dict['transporte']
                        if isinstance(transporte, dict):
                            data_transporte = transporte.get('data_transporte')
                            if data_transporte is not None and str(data_transporte).strip() not in ('', 'null'):
                                dt = self._parse_data_ate(data_transporte)
                                if dt is not None and dt <= data_ate:
                                    pecas_transportadas += 1
                    # Concretadas: data_concretagem <= data_ate
                    if peca.data_concretagem:
                        dc = peca.data_concretagem.date() if hasattr(peca.data_concretagem, 'date') else peca.data_concretagem
                        if dc <= data_ate:
                            pecas_concretadas += 1
                except Exception:
                    pass
        # NFs emitidas até data_ate
        if self.item_nf is not None:
            try:
                # Soma só linhas cujo codigo = item_nf deste tanque; outras linhas da mesma NF
                # (outros tanques) não entram na agregação.
                pecas_nfs_quantidade, nfs_emitidas_total = (
                    db.session.query(
                        func.coalesce(func.sum(NotaFiscalItem.quantidade), 0),
                        func.count(distinct(NotaFiscal.id)),
                    )
                    .select_from(NotaFiscalItem)
                    .join(NotaFiscal, NotaFiscal.id == NotaFiscalItem.nf_id)
                    .filter(
                        NotaFiscal.cnpj_emitente == CNPJS_MATRIZ,   
                        func.coalesce(func.lower(NotaFiscal.status_processamento), '')
                        != 'cancelada',
                        NotaFiscalItem.codigo.like(f'%{self.item_nf}%'),
                        func.date(NotaFiscal.data_emissao) <= data_ate,
                    )
                    .one()
                )
            except Exception:
                pecas_nfs_quantidade = 0
                nfs_emitidas_total = 0
        pecas_prontas_transportar = pecas_acabadas - pecas_transportadas
        pecas_em_estoque = pecas_concretadas - pecas_transportadas
        return {
            'concretadas': pecas_concretadas,
            'acabadas': pecas_acabadas,
            'transportadas': pecas_transportadas,
            'total_pecas': len(self.TanquesPecas),
            'em_estoque': pecas_em_estoque,
            'prontas_transportar': pecas_prontas_transportar,
            'nfs_emitidas_total': nfs_emitidas_total,
            'nfs_emitidas_quantidade': pecas_nfs_quantidade,
            'percas': pecas_perca
        }
class TanquesGrupos(db.Model):
    """
    Modelo para representar grupos de tanques
    """
    __tablename__ = 'TanquesGrupos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text, nullable=True)
    cor = db.Column(db.String(7), nullable=True)  # Código hexadecimal da cor
    icone = db.Column(db.String(50), nullable=True)  # Classe do ícone (ex: fas fa-water)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    tanques = db.relationship('Tanques', secondary='TanquesGruposItens', back_populates='grupos')
    
    def __repr__(self):
        return f'<TanquesGrupos {self.id} - {self.nome}>'
    
    def to_dict(self):
        """
        Converte o grupo para dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'cor': self.cor,
            'icone': self.icone,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None,
            'total_tanques': len(self.tanques) if self.tanques else 0
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
        # Remove as associações com tanques primeiro
        db.session.execute(
            db.text("DELETE FROM tanques_grupos WHERE grupo_id = :grupo_id"),
            {"grupo_id": self.id}
        )
        db.session.delete(self)
        db.session.commit()
    
    @classmethod
    def get_all(cls):
        """
        Retorna todos os grupos
        """
        return cls.query.order_by(cls.nome).all()
    
    def adicionar_tanque(self, tanque):
        """
        Adiciona um tanque ao grupo
        """
        if tanque not in self.tanques:
            self.tanques.append(tanque)
            db.session.flush()  # Usar flush ao invés de commit para permitir rollback se necessário
    
    def remover_tanque(self, tanque):
        """
        Remove um tanque do grupo
        """
        if tanque in self.tanques:
            self.tanques.remove(tanque)
            db.session.commit()
    
    @property
    def total_tanques(self):
        """
        Retorna o total de tanques no grupo
        """
        return len(self.tanques) if self.tanques else 0


# Tabela de associação entre tanques e grupos
tanques_grupos = db.Table('TanquesGruposItens',
    db.Column('id', db.Integer, primary_key=True, autoincrement=True),
    db.Column('tanque_id', db.Integer, db.ForeignKey('Tanques.id'), primary_key=False),
    db.Column('grupo_id', db.Integer, db.ForeignKey('TanquesGrupos.id'), primary_key=False),
    db.Column('data_associacao', db.DateTime, default=datetime.now),
    db.PrimaryKeyConstraint('id'),
)

class TanquesPecas(db.Model):
    __tablename__ = 'TanquesPecas'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50), nullable=False)
    altura = db.Column(db.DECIMAL(10, 2), nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    numero_sequencial = db.Column(db.Integer, nullable=False)
    numero_tanque = db.Column(db.Integer, nullable=True)
    volume = db.Column(db.DECIMAL(10, 2), nullable=True)
    data_prevista = db.Column(db.DateTime, nullable=True)
    data_concretagem = db.Column(db.DateTime, nullable=True)
    data_entrega = db.Column(db.DateTime, nullable=True)
    qualidade = db.Column(db.String(1000), nullable=True)
    
    # Relacionamento com tanque
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id', ondelete='CASCADE'), nullable=False)
    tanque = db.relationship('Tanques', backref=db.backref('TanquesPecas', lazy=True, cascade='all, delete-orphan'))
    
    # Relação com concretagens através da classe de associação    
    # Campos de auditoria
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def save(self):
        # Se for uma nova peça, atribui o próximo número sequencial
        if not self.id and not self.numero_sequencial:
            # Encontra o maior número sequencial para o tanque atual
            maior_sequencial = db.session.query(db.func.max(TanquesPecas.numero_sequencial))\
                .filter(TanquesPecas.tanque_id == self.tanque_id).scalar() or 0
            # Incrementa para obter o próximo número
            self.numero_sequencial = maior_sequencial + 1
        
        # Nova peça: data_producao só na raiz do JSON (evita duplicar em dados_adicionais)
        if not self.id:
            if not self.qualidade:
                qualidade_dict = {'data_producao': None}
                self.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)
            else:
                try:
                    qualidade_dict = json.loads(self.qualidade) if isinstance(self.qualidade, str) else self.qualidade
                    if not isinstance(qualidade_dict, dict):
                        qualidade_dict = {}
                    if 'data_producao' not in qualidade_dict:
                        qualidade_dict['data_producao'] = None
                    qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
                    self.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    qualidade_dict = {'data_producao': None}
                    self.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)
            
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
   
    def delete(self):
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        return f'<Peca {self.nome} ({self.tipo}) - #{self.numero_sequencial}>' 
    def produzir(self):
        """
        Produz a peça
        """
        if not self.qualidade:
            return False
        qualidade = json.loads(self.qualidade)
        if qualidade and 'data_producao' in qualidade:
            return True
    def get_series_de_pecas(self):
        """
        Retorna as séries de peças do tanque
        """
        try:
            qualidade = json.loads(self.qualidade)
            if qualidade and 'series' in qualidade:
                return qualidade['series']
            return []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return []
    
    def is_PF(self):
        return self.tipo == 'PF'
    def to_dict(self):
        """
        Retorna um dicionário com os campos da peça
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'tipo': self.tipo,
            'numero_sequencial': self.numero_sequencial,
            'numero_tanque': self.numero_tanque,
            'volume': self.volume,
            'data_prevista': self.data_prevista,
            'data_concretagem': self.data_concretagem,
            'data_entrega': self.data_entrega,
            'qualidade': self.qualidade,
        }
class TanquesProdutoComposto(db.Model):
    """
    Modelo para vincular tanques a produtos compostos
    Permite associar um produto composto específico a cada tanque
    """
    __tablename__ = 'TanquesProdutoComposto'
    
    id = db.Column(db.Integer, primary_key=True)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id', ondelete='CASCADE'), nullable=False)
    tipo_peca = db.Column(db.String(50), nullable=False)
    produto_composto_id = db.Column(db.Integer, db.ForeignKey('ProdutoComposto.id', ondelete='CASCADE'), nullable=False)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    tanque = db.relationship('Tanques', backref='produtos_compostos_vinculados')
    produto_composto = db.relationship('ProdutoComposto', backref='tanques_vinculados')
    
    # Um tanque pode ter o mesmo produto composto para vários tipos de peça; duplicata = mesmo tanque+produto+tipo
    __table_args__ = (
        db.UniqueConstraint(
            'tanque_id', 'produto_composto_id', 'tipo_peca',
            name='uq_tanque_produto_composto_tipo',
        ),
    )
    
    def save(self):
        """Salva a vinculação no banco de dados"""
        db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Remove a vinculação do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        return f'<TanqueProdutoComposto Tanque: {self.tanque_id}, Produto: {self.produto_composto_id}>'

