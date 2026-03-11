"""
Modelos do módulo PLR (Participação nos Lucros e Resultados).
"""
from datetime import datetime
from sqlalchemy import JSON, Text
from models.database import db


class ModeloPLR(db.Model):
    """
    Modelo de PLR: nome, departamentos vinculados, forma de cálculo e pesos dos colaboradores,
    e forma de cálculo final.
    """
    __tablename__ = 'PlrModelos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    # Forma de cálculo por colaborador (ex: "media_avaliacoes", "soma_ponderada")
    forma_calculo_colaborador = db.Column(db.String(100), nullable=True)
    # Pesos por tipo de avaliação ou critério (JSON: {"desempenho": 0.5, "competencia": 0.5})
    pesos_colaboradores = db.Column(JSON, nullable=True)
    # Forma de cálculo final (ex: "ponderada_salario", "igualitaria", "custom")
    forma_calculo_final = db.Column(db.String(100), nullable=True)
    # Configuração adicional em JSON para fórmulas customizadas
    config_calculo_final = db.Column(JSON, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    departamentos = db.relationship(
        'Departamento',
        secondary='PlrModelosDepartamentos',
        backref=db.backref('PlrModelos', lazy='dynamic'),
        lazy='joined'
    )
    avaliacoes = db.relationship('PLRColaborador', backref='modelo_plr', lazy='dynamic')

    def __repr__(self):
        return f'<ModeloPLR {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'ativo': self.ativo,
            'forma_calculo_colaborador': self.forma_calculo_colaborador,
            'pesos_colaboradores': self.pesos_colaboradores,
            'forma_calculo_final': self.forma_calculo_final,
            'config_calculo_final': self.config_calculo_final,
            'departamento_ids': [d.id for d in self.departamentos],
        }


# Tabela associativa N:N entre ModeloPLR e Departamento
modelos_plr_departamentos = db.Table(
    'PlrModelosDepartamentos',
    db.Column('PlrModelo_id', db.Integer, db.ForeignKey('PlrModelos.id', ondelete='CASCADE'), primary_key=True),
    db.Column('departamento_id', db.Integer, db.ForeignKey('departamentos.id', ondelete='CASCADE'), primary_key=True),
)


class PLRColaborador(db.Model):
    """
    Avaliação PLR do colaborador: obra (centro de custo), equipe alocada (lista texto),
    colaborador, avaliação (JSON com um ou mais tipos) e data.
    """
    __tablename__ = 'PlrAvaliacoes'

    id = db.Column(db.Integer, primary_key=True)
    PlrModelo_id = db.Column(db.Integer, db.ForeignKey('PlrModelos.id', ondelete='RESTRICT'), nullable=True)
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id', ondelete='SET NULL'), nullable=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id', ondelete='CASCADE'), nullable=False)
    # Equipe alocada: lista de nomes em JSON, ex: ["Equipe A", "Equipe B"]
    equipe_alocada = db.Column(JSON, nullable=True)
    # Avaliação em JSON: pode ter vários tipos, ex: [{"tipo": "desempenho", "valor": 8.5}, {"tipo": "competencia", "valor": 9}]
    avaliacao = db.Column(JSON, nullable=False)
    data = db.Column(db.Date, nullable=False)
    observacoes = db.Column(Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    centro_custo = db.relationship('CentroCusto', backref=db.backref('plr_avaliacoes', lazy='dynamic'))
    colaborador = db.relationship('Colaborador', backref=db.backref('plr_avaliacoes', lazy='dynamic'))

    def __repr__(self):
        return f'<PLRColaborador colaborador_id={self.colaborador_id} data={self.data}>'

    def to_dict(self):
        return {
            'id': self.id,
            'PlrModelo_id': self.PlrModelo_id,
            'centro_custo_id': self.centro_custo_id,
            'centro_custo_nome': self.centro_custo.nome if self.centro_custo else None,
            'colaborador_id': self.colaborador_id,
            'colaborador_nome': self.colaborador.nome if self.colaborador else None,
            'equipe_alocada': self.equipe_alocada,
            'avaliacao': self.avaliacao,
            'data': self.data.isoformat() if self.data else None,
            'observacoes': self.observacoes,
        }

    def nota_media_avaliacao(self):
        """
        Retorna a média das avaliações. Se os itens tiverem 'peso', usa média ponderada;
        caso contrário, usa média aritmética.
        """
        if not self.avaliacao:
            return None
        if isinstance(self.avaliacao, list):
            soma_ponderada = 0.0
            soma_pesos = 0.0
            valores_simples = []
            for item in self.avaliacao:
                if isinstance(item, dict) and 'valor' in item:
                    try:
                        v = float(item['valor'])
                    except (TypeError, ValueError):
                        continue
                    peso = item.get('peso')
                    if peso is not None:
                        try:
                            p = float(peso)
                            soma_ponderada += v * p
                            soma_pesos += p
                        except (TypeError, ValueError):
                            valores_simples.append(v)
                    else:
                        valores_simples.append(v)
                elif isinstance(item, (int, float)):
                    valores_simples.append(float(item))
            if soma_pesos > 0:
                return soma_ponderada / soma_pesos
            return sum(valores_simples) / len(valores_simples) if valores_simples else None
        if isinstance(self.avaliacao, dict) and 'valor' in self.avaliacao:
            try:
                return float(self.avaliacao['valor'])
            except (TypeError, ValueError):
                pass
        return None


class EfetivoPLR(db.Model):
    """
    Efetivo (quadro de funcionários) importado por ano/mês para uso em PLR.
    Campos: ano, mes, cpf, nome, funcao, salario, data_nascimento, data_demissao, secao, data_admissao, chapa.
    """
    __tablename__ = 'PlrEfetivos'

    id = db.Column(db.Integer, primary_key=True)
    ano = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)  # 1-12
    cpf = db.Column(db.String(20), nullable=True)
    nome = db.Column(db.String(200), nullable=True)
    funcao = db.Column(db.String(150), nullable=True)
    salario = db.Column(db.Numeric(12, 2), nullable=True)
    data_nascimento = db.Column(db.Date, nullable=True)
    data_demissao = db.Column(db.Date, nullable=True)
    secao = db.Column(db.String(150), nullable=True)
    data_admissao = db.Column(db.Date, nullable=True)
    chapa = db.Column(db.String(50), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<EfetivoPLR {self.ano}/{self.mes} {self.nome or self.cpf}>'

    def to_dict(self):
        return {
            'id': self.id,
            'ano': self.ano,
            'mes': self.mes,
            'cpf': self.cpf,
            'nome': self.nome,
            'funcao': self.funcao,
            'salario': float(self.salario) if self.salario is not None else None,
            'data_nascimento': self.data_nascimento.isoformat() if self.data_nascimento else None,
            'data_demissao': self.data_demissao.isoformat() if self.data_demissao else None,
            'secao': self.secao,
            'data_admissao': self.data_admissao.isoformat() if self.data_admissao else None,
            'chapa': self.chapa,
        }
