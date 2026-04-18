"""Usinagens de concreto, materiais executados e rompimentos de CP."""

from datetime import datetime
from decimal import Decimal
import traceback

from flask import json
from flask_login import current_user
from sqlalchemy import JSON
from sqlalchemy.sql import func

from models.database import db
from models.produto_composto import ProdutoComposto
from models.estoque import Estoque, EstoqueMovimentacoes


class ConcretoUsinagens(db.Model):
    """
    Modelo simplificado para representar usinagem de concreto
    """
    __tablename__ = 'ConcretoUsinagens'

    id = db.Column(db.Integer, primary_key=True)
    serie = db.Column(db.String(100), unique=True, nullable=False)
    data_usinagem = db.Column(db.DateTime, nullable=False)
    produtoCompostoId = db.Column(db.Integer, db.ForeignKey('ProdutoComposto.id'), nullable=True)
    flow = db.Column(db.String(50), nullable=True)
    volume = db.Column(db.Numeric(10, 2), nullable=False)
    nota = db.Column(db.String(50), nullable=True)
    dados_adicionais = db.Column(JSON, nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    produto_composto = db.relationship('ProdutoComposto', foreign_keys=[produtoCompostoId])
    materiais = db.relationship('ConcretoUsinagensMateriais', backref='usinagem', cascade='all, delete-orphan')

    def adicionar_material(self, material, quantidade_executada=None, unidade=None, conversao_unidade_id=None):
        """Adiciona um material executado na usinagem"""
        for item in self.materiais:
            if item.material_id == material.id:
                if quantidade_executada is not None:
                    item.quantidade_executada = quantidade_executada
                if unidade:
                    if hasattr(unidade, 'nome'):
                        item.unidade = unidade.nome
                    else:
                        item.unidade = unidade
                return item

        nome_unidade_para_salvar = 'N/A'
        if unidade:
            if hasattr(unidade, 'nome'):
                nome_unidade_para_salvar = unidade.nome
            elif isinstance(unidade, str):
                nome_unidade_para_salvar = unidade
        elif material and material.unidade and hasattr(material.unidade, 'nome'):
            nome_unidade_para_salvar = material.unidade.nome
        elif material and isinstance(material.unidade, str):
            nome_unidade_para_salvar = material.unidade

        item = ConcretoUsinagensMateriais(
            usinagem_id=self.id,
            material_id=material.id,
            quantidade_executada=quantidade_executada,
            unidade=nome_unidade_para_salvar,
            conversao_unidade_id=conversao_unidade_id
        )
        self.materiais.append(item)
        return item

    def remover_material(self, material_id):
        """Remove um material da usinagem"""
        for item in self.materiais:
            if item.material_id == material_id:
                self.materiais.remove(item)
                return True
        return False

    def calcular_materiais(self):
        """Calcula a quantidade de materiais necessários para o volume de concreto baseado no produto composto"""
        resultado = []
        if not self.produto_composto:
            return resultado

        for componente in self.produto_composto.componentes:
            if componente.estoque and componente.estoque.tipo_item == 'material':
                quantidade_total = Decimal(str(componente.quantidade)) * self.volume

                resultado.append({
                    'material': componente.estoque.material,
                    'quantidade': quantidade_total,
                    'unidade': componente.estoque.material.unidade_obj.nome if componente.estoque.material and componente.estoque.material.unidade_obj else 'N/A',
                    'influenciado_umidade': False
                })

        return resultado

    def save(self):
        """Salva a usinagem no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Remove a usinagem do banco de dados"""
        materiais = ConcretoUsinagensMateriais.query.filter_by(usinagem_id=self.id).all()
        for material in materiais:
            if material.movimentacao_estoque_id:
                movimentacao = EstoqueMovimentacoes.query.filter_by(id=material.movimentacao_estoque_id).first()
                if movimentacao:
                    movimentacao.delete()
        db.session.delete(self)
        db.session.commit()
        return self

    def tem_redozagem(self):
        """Verifica se há redozagem na usinagem"""
        for item in self.materiais:
            if item.redozagem:
                return True
        return False

    def baixar_materiais_estoque(self, usuario_id=None):
        """
        Baixa os materiais utilizados na usinagem do estoque.
        """
        from models.estoque import Estoque, EstoqueMovimentacoes
        from models.database import db
        from decimal import Decimal

        resultados = []
        print(f"============ INÍCIO DA BAIXA DE MATERIAIS - USINAGEM ID: {self.id} ============")
        print(f"Total de materiais na usinagem: {len(self.materiais)}")

        try:
            for i, item_material in enumerate(self.materiais):
                print(f"\nProcessando material {i+1}/{len(self.materiais)}: ID={item_material.material_id}, Material={item_material.material.nome if item_material.material else 'N/A'}")

                if not item_material.quantidade_executada or float(item_material.quantidade_executada) == 0:
                    print(f"Material sem quantidade executada. Pulando.")
                    resultados.append((False, f"Material {item_material.material.nome} sem quantidade executada", item_material.material_id))
                    continue

                print(f"Quantidade executada: {item_material.quantidade_executada}")

                item_estoque = Estoque.query.filter_by(
                    material_id=item_material.material_id,
                    tipo_item='material'
                ).first()

                if not item_estoque:
                    print(f"Material não encontrado no estoque. Criando novo registro.")
                    item_estoque = Estoque(
                        material_id=item_material.material_id,
                        tipo_item='material',
                        quantidade=0,
                        usuario_id=usuario_id or 1
                    )
                    db.session.add(item_estoque)
                    db.session.flush()
                    print(f"Novo item de estoque criado com ID: {item_estoque.id}")
                else:
                    print(f"Material encontrado no estoque. ID: {item_estoque.id}, Quantidade atual: {item_estoque.quantidade}")

                quantidade_a_baixar = Decimal(str(item_material.quantidade_executada))

                if item_estoque.quantidade < quantidade_a_baixar:
                    print(f"Quantidade insuficiente em estoque. Necessário: {quantidade_a_baixar}, Disponível: {item_estoque.quantidade}")
                    resultados.append((False,
                        f"Quantidade insuficiente de {item_material.material.nome} em estoque. Necessário: {quantidade_a_baixar}, Disponível: {item_estoque.quantidade}",
                        item_material.material_id
                    ))
                    continue

                try:
                    if EstoqueMovimentacoes.query.filter_by(origem_id=self.id, origem_tipo='usinagem_concreto', estoque_id=item_estoque.id).count() == 0:
                        observacao = f"Consumo em usinagem de concreto #{self.id} - Série: {self.serie}"
                        movimentacao = EstoqueMovimentacoes.criar_baixa_usinagem(
                            estoque_id=item_estoque.id,
                            quantidade=quantidade_a_baixar,
                            data_movimento=self.data_usinagem,
                            origem_id=self.id,
                            usuario_id=usuario_id or 1,
                            observacao=observacao
                        )
                    elif item_material.redozagem:
                        observacao = f"Consumo em usinagem de concreto redozado material {item_material.material.id} #{self.id} - Série: {self.serie}"
                        movimentacao = EstoqueMovimentacoes.criar_baixa_usinagem(
                            estoque_id=item_estoque.id,
                            quantidade=quantidade_a_baixar,
                            data_movimento=self.data_usinagem,
                            origem_id=self.id,
                            usuario_id=usuario_id or 1,
                            observacao=observacao
                        )
                    else:
                        continue

                    print(f"Movimentação criada com ID: {movimentacao.id if movimentacao else 'N/A'}")
                    item_material.movimentacao_estoque_id = movimentacao.id
                    item_material.save()
                    resultados.append((True,
                        f"Baixado {quantidade_a_baixar} de {item_material.material.nome} do estoque",
                        item_material.material_id
                    ))
                except Exception as e:
                    print(f"Erro ao criar movimentação: {str(e)}")
                    print(traceback.format_exc())
                    resultados.append((False,
                        f"Erro ao realizar baixa de {item_material.material.nome}: {str(e)}",
                        item_material.material_id
                    ))

            print(f"\nRealizando commit das alterações no banco de dados")
            db.session.commit()
            print(f"Commit concluído com sucesso")

        except Exception as e:
            db.session.rollback()
            print(f"ERRO GERAL ao baixar materiais: {str(e)}")
            print(traceback.format_exc())
            resultados.append((False, f"Erro ao processar baixa de materiais: {str(e)}", None))

        print(f"============ FIM DA BAIXA DE MATERIAIS ============")
        return resultados

    def __repr__(self):
        return f'<UsinagemConcreto {self.id} - Série: {self.serie}, Data: {self.data_usinagem}, Volume: {self.volume}m³>'

    def get_caminhao(self):
        """Retorna o caminhão baseado no número da série."""
        primeira_serie = ConcretoUsinagens.query.filter(func.date(ConcretoUsinagens.data_usinagem) == self.data_usinagem.date()).order_by(ConcretoUsinagens.data_usinagem.asc()).first().serie

        if primeira_serie == self.serie:
            return "01"
        else:
            return str(self.serie - primeira_serie + 1)

    def produzir(self, usuario_id=None, total=False):
        """Produz a usinagem de concreto"""
        mov = EstoqueMovimentacoes.query.filter(
            EstoqueMovimentacoes.origem_tipo.like('%usinagem_concreto%'),
            EstoqueMovimentacoes.origem_id == self.id).all()
        if mov:
            return False

        if usuario_id is None:
            usuario_id = current_user.id if current_user and hasattr(current_user, 'id') else 1
        dados_adicionais = {}
        if self.dados_adicionais:
            try:
                dados_adicionais = json.loads(self.dados_adicionais) if isinstance(self.dados_adicionais, str) else self.dados_adicionais
            except (json.JSONDecodeError, TypeError):
                dados_adicionais = {}
            if 'data_producao' in dados_adicionais and dados_adicionais.get('data_producao') is not None:
                if not total:
                    return False

        print(f"Produzindo usinagem de concreto #{self.id} - Série: {self.serie} - Data: {self.data_usinagem} - Volume: {self.volume} - Produto composto ID: {self.produtoCompostoId}")
        produto = ProdutoComposto.query.get(self.produtoCompostoId)
        if not produto:
            print(f"  AVISO: Usinagem de concreto #{self.id} - Série: {self.serie} - Data: {self.data_usinagem} - Volume: {self.volume} - Produto composto não encontrado. 1")
            return False
        _produtos_processados = set()
        _materiais_necessarios = {}
        produto.produzir(
            quantidade=self.volume,
            data_movimento=self.data_usinagem,
            usuario_id=usuario_id,
            log=False,
            produtos_processados=_produtos_processados,
            materiais_necessarios=_materiais_necessarios,
            traco=False
        )
        print(f"Materiais necessários: {len(_materiais_necessarios)}")
        if _materiais_necessarios:
            for info in _materiais_necessarios.values():
                estoque = info['estoque']
                quantidade_total = info['quantidade']
                produto_id = info['produto_id']
                print(f"  -> Componente material: {estoque.material.nome} - Quantidade total: {quantidade_total}")
                mov = EstoqueMovimentacoes()
                mov.remover(
                    quantidade=quantidade_total,
                    estoque_id=estoque.id,
                    origem_id=self.id,
                    origem_tipo='usinagem_concreto',
                    usuario_id=usuario_id,
                    motivo=f'Produção da usinagem de concreto #{self.id} - Série: {self.serie} - Quantidade: {quantidade_total}',
                    log=True)
                mov.data_movimento = self.data_usinagem
                mov.save()

        dados_adicionais['data_producao'] = datetime.now().isoformat()
        self.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
        self.save()
        db.session.commit()
        return True


class ConcretoUsinagensMateriais(db.Model):
    """
    Modelo para representar materiais utilizados em uma usinagem
    """
    __tablename__ = 'ConcretoUsinagensMateriais'

    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('ConcretoUsinagens.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('Materiais.id'), nullable=False)
    quantidade_executada = db.Column(db.Numeric(10, 2), nullable=True)
    unidade = db.Column(db.String(20), nullable=False)
    conversao_unidade_id = db.Column(db.Integer, nullable=True)
    movimentacao_estoque_id = db.Column(db.Integer, nullable=True)
    material = db.relationship('Materiais')
    redozagem = db.Column(db.Boolean, default=False)

    def save(self):
        """Salva o material da usinagem no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Remove o material da usinagem do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self

    def __repr__(self):
        return f'<UsinagemMaterial {self.id} - Material: {self.material_id}, Qtd: {self.quantidade_executada} {self.unidade}>'


class ConcretoUsinagensRompimentos(db.Model):
    """
    Modelo para representar rompimentos de corpos de prova por usinagem
    """
    __tablename__ = 'ConcretoUsinagensRompimentos'

    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('ConcretoUsinagens.id', ondelete='CASCADE'), nullable=True)
    numero_serie = db.Column(db.Integer, nullable=False)
    data_moldagem = db.Column(db.DateTime, nullable=True)
    data_rompimento = db.Column(db.DateTime, nullable=False)
    resultado = db.Column(db.Numeric(10, 2), nullable=True)
    fator_conversao = db.Column(db.Numeric(5, 2), nullable=True, default=1.2)
    idade_cp = db.Column(db.Integer, nullable=True)
    tipo_rompimento = db.Column(db.String(50), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    usinagem = db.relationship('ConcretoUsinagens', backref=db.backref('rompimentos', lazy=True, cascade="all, delete-orphan"))

    def save(self):
        """Salva o rompimento no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Remove o rompimento do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self

    def is_exist(self):
        """Verifica se o rompimento existe no banco de dados"""
        return ConcretoUsinagensRompimentos.query.filter_by(
            numero_serie=self.numero_serie,
            data_rompimento=self.data_rompimento,
            tipo_rompimento=self.tipo_rompimento,
            resultado=self.resultado,
            data_moldagem=self.data_moldagem,
            usinagem_id=self.usinagem_id).first() is not None

    def __repr__(self):
        return f'<RompimentoCorpoProva {self.id} - Usinagem: {self.usinagem_id}, Série: {self.numero_serie}, Idade: {self.idade_cp} dias>'
