from datetime import datetime
from models.database import db
from models.material import Material
from models.epi import EPI
from models.nota_fiscal import NotaFiscalItem
from models.usuario import Usuario
from models.centro_custo import CentroCusto
from decimal import Decimal
class Estoque(db.Model):
    """
    Modelo para controle unificado de estoque
    """
    __tablename__ = 'estoque'
    
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=True)
    material = db.relationship('Material', backref='estoque_items')
    epi_id = db.Column(db.Integer, db.ForeignKey('epis.id'), nullable=True)
    epi = db.relationship('EPI', backref='estoque_items')
    tipo_item = db.Column(db.String(20), nullable=False)  # 'material', 'epi', 'usinagem', etc.
    
    quantidade = db.Column(db.Numeric(15, 4), nullable=False, default=0)
    quantidade_minima = db.Column(db.Numeric(15, 4), default=0)
    quantidade_maxima = db.Column(db.Numeric(15, 4), default=0)
    localizacao = db.Column(db.String(100))
    lote = db.Column(db.String(50))
    data_validade = db.Column(db.Date)
    
    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=True)
    centro_custo = db.relationship('CentroCusto', backref='items_estoque')
    
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    usuario = db.relationship('Usuario', backref='items_estoque')
    
    def save(self):
        """
        Salva o item de estoque no banco de dados
        """
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o item de estoque do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    @property
    def status_estoque(self):
        """
        Retorna o status do estoque baseado na quantidade atual
        """
        if self.quantidade <= 0:
            return "Esgotado"
        elif self.quantidade < self.quantidade_minima:
            return "Crítico"
        elif self.quantidade > self.quantidade_maxima and self.quantidade_maxima > 0:
            return "Excesso"
        else:
            return "Normal"
    
    @property
    def status_validade(self):
        """
        Retorna o status da validade do item
        """
        if not self.data_validade:
            return "Sem validade"
            
        hoje = datetime.now().date()
        dias_restantes = (self.data_validade - hoje).days
        
        if dias_restantes < 0:
            return "Vencido"
        elif dias_restantes <= 30:
            return "Próximo ao vencimento"
        else:
            return "Válido"
    
    def get_estoque_atual(self):
        movimentacoes = MovimentacaoEstoque.query.filter_by(estoque_id = self.id).order_by(MovimentacaoEstoque.data_movimento.desc()).all()
        saldo_anterior = 0
        for movimentacao in movimentacoes:
            if movimentacao.tipo_movimento == 'entrada':
                saldo_anterior += Decimal(str(movimentacao.quantidade))
            elif movimentacao.tipo_movimento == 'saida':
                saldo_anterior -= Decimal(str(movimentacao.quantidade))
        return saldo_anterior
    @property
    def valor_estimado(self):
        """
        Calcula o valor estimado do item em estoque
        """
        # Esta função pode ser implementada consultando o preço médio ou último preço
        # Será implementada na versão 2.0
        return 0
    
    def __repr__(self):
        """
        Representação em string do item de estoque
        """
        tipo = self.tipo_item.capitalize()
        nome_item = ""
        
        if self.material:
            nome_item = self.material.nome
        elif self.epi:
            nome_item = self.epi.material.nome if self.epi.material else "EPI sem nome"
        
        return f'<Estoque {tipo} - {nome_item} - Qtd: {self.quantidade}>'


class MovimentacaoEstoque(db.Model):
    """
    Modelo para registrar movimentações de estoque
    """
    __tablename__ = 'movimentacoes_estoque'
    
    id = db.Column(db.Integer, primary_key=True)
    estoque_id = db.Column(db.Integer, db.ForeignKey('estoque.id'), nullable=False)
    estoque = db.relationship('Estoque', backref='movimentacoes')
    
    tipo_movimento = db.Column(db.String(20), nullable=False)  # 'entrada', 'saida', 'ajuste', 'transferencia'
    quantidade = db.Column(db.Numeric(15, 4), nullable=False)
    data_movimento = db.Column(db.DateTime, default=datetime.now, nullable=False)
    
    nota_fiscal_item_id = db.Column(db.Integer, db.ForeignKey('nf_itens.id'), nullable=True)
    nota_fiscal_item = db.relationship('NotaFiscalItem', backref='movimentacoes_estoque')
    
    origem_id = db.Column(db.Integer, nullable=True)  # ID do registro de origem (solicitação, entrega EPI, etc)
    origem_tipo = db.Column(db.String(50), nullable=True)  # Tipo do registro de origem
    
    observacao = db.Column(db.Text)
    entregas_epi = db.relationship('EntregaEPI', back_populates='movimentacao_estoque')
    # Controle de auditoria
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    usuario = db.relationship('Usuario', backref='movimentacoes_realizadas')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        #print(f"kwargs: {kwargs}")
    @classmethod
    def get_historico_saldo_para_grafico(cls, estoque_id, data_inicio=None, data_fim=None):
        """
        Retorna o histórico de saldo para um item de estoque específico,
        calculado a partir de suas movimentações.

        Args:
            estoque_id (int): ID do item de estoque.
            data_inicio (datetime.date, optional): Data de início do período.
            data_fim (datetime.date, optional): Data de fim do período.

        Returns:
            list: Lista de dicionários {"data": data_formatada, "saldo": saldo_acumulado}
        """
        query = cls.query.filter_by(estoque_id=estoque_id)

        if data_inicio:
            query = query.filter(MovimentacaoEstoque.data_movimento >= data_inicio)
        if data_fim:
            # Adicionar um dia para incluir movimentações no dia final
            from datetime import timedelta
            query = query.filter(MovimentacaoEstoque.data_movimento < data_fim + timedelta(days=1))

        movimentacoes = query.order_by(MovimentacaoEstoque.data_movimento.asc()).all()

        historico_saldo = []
        saldo_acumulado = Decimal('0.0') # Inicia com saldo zero

        # Se houver um data_inicio, precisamos calcular o saldo até essa data
        # para que o gráfico comece com o valor correto no período filtrado.
        # No entanto, para simplificar e dado que o padrão é mostrar tudo,
        # vamos sempre calcular a partir do zero para todas as movimentações
        # retornadas pela query. O frontend controlará o zoom/período visualizado.

        for mov in movimentacoes:
            if mov.tipo_movimento == 'entrada':
                saldo_acumulado += mov.quantidade
            elif mov.tipo_movimento == 'saida':
                saldo_acumulado -= mov.quantidade
            elif mov.tipo_movimento == 'ajuste':
                # Para 'ajuste', o 'quantidade' na movimentação representa o NOVO saldo.
                # No entanto, a lógica atual do 'save' da MovimentacaoEstoque parece
                # atualizar o Estoque.quantidade para o valor do ajuste, o que é correto.
                # Mas, para o cálculo do histórico aqui, precisamos ver como o saldo foi
                # afetado PELA MOVIMENTAÇÃO.
                #
                # Se a movimentação de ajuste guarda o NOVO saldo total,
                # então o saldo_acumulado deve se tornar esse valor.
                # Se ela guarda a DIFERENÇA do ajuste, então devemos somar/subtrair.
                #
                # Assumindo que o método 'save' da MovimentacaoEstoque ao fazer ajuste
                # já coloca o saldo correto no Estoque.quantidade e que a 'quantidade'
                # na MovimentacaoEstoque do tipo 'ajuste' é o novo saldo total.
                #
                # Revisando o controller: na rota 'editar', quando a quantidade é alterada,
                # uma movimentação de 'ajuste' é criada com a 'nova_quantidade'.
                # E o Estoque.quantidade é atualizado para essa nova_quantidade.
                # Portanto, para 'ajuste', o saldo_acumulado deve ser definido para mov.quantidade.
                saldo_acumulado = mov.quantidade

            # Formatar a data para string (ex: YYYY-MM-DD HH:MM:SS) para o Plotly
            historico_saldo.append({
                "data": mov.data_movimento.strftime('%Y-%m-%d %H:%M:%S'),
                "saldo": float(saldo_acumulado) # Plotly geralmente prefere float
            })
        
        return historico_saldo
    
    @classmethod
    def criar_baixa_usinagem(cls, estoque_id, quantidade, data_movimento, origem_id, usuario_id, observacao=None):
        """
        Método de classe para criar uma movimentação de saída específica para usinagem de concreto.
        
        Args:
            estoque_id: ID do item de estoque
            quantidade: Quantidade a ser baixada
            data_movimento: Data da movimentação
            origem_id: ID da usinagem
            usuario_id: ID do usuário que está realizando a operação
            observacao: Observação opcional sobre a movimentação
            
        Returns:
            MovimentacaoEstoque: Nova instância da movimentação
        """
        from decimal import Decimal
        import traceback
        
        try:
            print(f"Criando movimentação de estoque para usinagem:")
            print(f"  - estoque_id: {estoque_id}")
            print(f"  - quantidade: {quantidade}")
            print(f"  - data_movimento: {data_movimento}")
            print(f"  - origem_id: {origem_id}")
            print(f"  - usuario_id: {usuario_id}")
            
            # Verificar se o estoque existe
            estoque = Estoque.query.get(estoque_id)
            if not estoque:
                print(f"Erro: Estoque ID {estoque_id} não encontrado")
                raise ValueError(f"Estoque ID {estoque_id} não encontrado")
            
            # Verificar quantidade
            if not quantidade or quantidade <= 0:
                print(f"Erro: Quantidade inválida: {quantidade}")
                raise ValueError(f"Quantidade inválida para movimentação: {quantidade}")
            
            # Verificar disponibilidade
            if estoque.quantidade < quantidade:
                print(f"Erro: Quantidade em estoque insuficiente: {estoque.quantidade} < {quantidade}")
                raise ValueError(f"Quantidade insuficiente em estoque. Disponível: {estoque.quantidade}, Necessário: {quantidade}")
                
            # Criar a movimentação
            movimentacao = cls(
                estoque_id=estoque_id,
                tipo_movimento='saida',
                quantidade=Decimal(str(quantidade)),
                data_movimento=data_movimento,
                origem_id=origem_id,
                origem_tipo='usinagem_concreto',
                observacao=observacao or f"Consumo em usinagem de concreto #{origem_id}",
                usuario_id=usuario_id
            )
            
            # Atualizar o estoque
            quantidade_anterior = estoque.quantidade
            estoque.quantidade -= Decimal(str(quantidade))
            print(f"Estoque atualizado: {quantidade_anterior} - {quantidade} = {estoque.quantidade}")
            
            # Adicionar ao banco de dados
            db.session.add(estoque)
            db.session.add(movimentacao)
            db.session.flush()
            
            return movimentacao
            
        except Exception as e:
            print(f"Erro ao criar movimentação: {str(e)}")
            print(traceback.format_exc())
            raise

    def adicionar(self,quantidade,estoque_id,origem_id,origem_tipo,usuario_id,motivo=None):
        """
        Cria uma nova movimentação de estoque de entrada
        """
        print(f"Adicionando {quantidade} item(s) ao estoque3")
        estoque = Estoque.query.get(estoque_id)
        if not estoque:
            raise ValueError(f"Estoque ID {estoque_id} não encontrado")
        print(f"Adicionando {quantidade} item(s) ao estoque4")
        if motivo:
            observacao = f'Entrada de estoque #{origem_tipo} #{origem_id} - {motivo}'
        else:
            observacao = f'Entrada de estoque #{origem_tipo} #{origem_id}'
        self.quantidade = quantidade
        self.estoque_id = estoque_id
        self.origem_id = origem_id
        self.origem_tipo = origem_tipo
        self.usuario_id = usuario_id
        self.observacao = observacao
        self.tipo_movimento = 'entrada'
    
    def remover(self,quantidade,estoque_id,origem_id,origem_tipo,usuario_id,motivo=None):
        """
        Cria uma nova movimentação de estoque de saída
        """
        estoque = Estoque.query.get(estoque_id)
        if not estoque:
            raise ValueError(f"Estoque ID {estoque_id} não encontrado") 
        self.quantidade = quantidade
        self.estoque_id = estoque_id
        self.origem_id = origem_id
        self.origem_tipo = origem_tipo
        self.usuario_id = usuario_id
        if motivo:
            observacao = f'Saída de estoque #{origem_tipo} #{origem_id} - {motivo}'
        else:
            observacao = f'Saída de estoque #{origem_tipo} #{origem_id}'
        self.observacao = observacao
        self.tipo_movimento = 'saida'

    def Ajuste(self,quantidade,estoque_id,origem_id,origem_tipo,usuario_id):
        """
        Cria uma nova movimentação de estoque
        """
        estoque = Estoque.query.get(estoque_id)
        if not estoque:
            raise ValueError(f"Estoque ID {estoque_id} não encontrado")
        diferenca = quantidade - estoque.get_estoque_atual()
        if diferenca == 0:
            raise ValueError(f"A quantidade ajustada é igual à quantidade atual do estoque")
        if diferenca > 0:
            tipo_movimento = 'entrada'
        else:
            tipo_movimento = 'saida'
        quantidade = abs(diferenca)
        self.quantidade = quantidade
        self.estoque_id = estoque_id
        self.origem_id = origem_id
        self.origem_tipo = origem_tipo
        self.usuario_id = usuario_id
        self.observacao = f'Ajuste de estoque #{origem_tipo} #{origem_id}'
        self.tipo_movimento = tipo_movimento

    def save(self):
        """
        Salva a movimentação de estoque e atualiza o estoque
        """
        import traceback
        
        try:
            print(f"Iniciando save() de MovimentacaoEstoque: tipo={self.tipo_movimento}, quantidade={self.quantidade}, estoque_id={self.estoque_id}")
            if self.estoque_id:
                self.estoque = Estoque.query.get(self.estoque_id)
            # Atualizar quantidade do estoque baseado no tipo de movimento
            if self.estoque:
                estoque_anterior = self.estoque.quantidade
            
                if self.tipo_movimento == 'entrada':
                    self.estoque.quantidade += self.quantidade
                    print(f"Movimentação ENTRADA: {estoque_anterior} + {self.quantidade} = {self.estoque.quantidade}")
                    
                elif self.tipo_movimento == 'saida':
                    if self.estoque.quantidade >= self.quantidade:
                        self.estoque.quantidade -= self.quantidade
                        print(f"Movimentação SAÍDA: {estoque_anterior} - {self.quantidade} = {self.estoque.quantidade}")
                    else:
                        print(f"ERRO: Quantidade insuficiente. Em estoque: {self.estoque.quantidade}, Tentando baixar: {self.quantidade}")
                        raise ValueError(f"Quantidade insuficiente em estoque. Disponível: {self.estoque.quantidade}, Necessário: {self.quantidade}")
                
                elif self.tipo_movimento == 'ajuste':
                    print(f"Movimentação AJUSTE: {estoque_anterior} -> {self.quantidade}")
                    self.estoque.quantidade = self.quantidade
                
                # Garante que a quantidade nunca será negativa
                if self.estoque.quantidade < 0:
                    print(f"AVISO: Quantidade negativa corrigida para 0")
                    self.estoque.quantidade = 0
                
                # Importante: atualizar o estoque no banco de dados
                db.session.add(self.estoque)
            else:
                print(f"ERRO: Estoque não encontrado para ID {self.estoque_id}")
        
        # Adiciona a movimentação ao banco
            if not self.id:  # Se for um novo registro
                db.session.add(self)
            
                # Executa o commit para salvar as alterações
                db.session.flush()  # Garante que os objetos tenham IDs
                print(f"Movimentação de estoque criada com ID {self.id}")
                
                db.session.commit()
                print(f"Transação concluída com sucesso")
                return True
            
        except Exception as e:
            db.session.rollback()
            print(f"ERRO ao salvar movimentação de estoque: {str(e)}")
            print(traceback.format_exc())
            raise e

    def saldo_anterior(self,data_movimento=None):
        if data_movimento is None:
            data_movimento = self.data_movimento
        movimentacoes = MovimentacaoEstoque.query.filter(MovimentacaoEstoque.data_movimento < data_movimento,MovimentacaoEstoque.estoque_id == self.estoque_id).order_by(MovimentacaoEstoque.data_movimento.desc()).all()
        saldo_anterior = 0
        for movimentacao in movimentacoes:
            if movimentacao.tipo_movimento == 'entrada':
                saldo_anterior += Decimal(str(movimentacao.quantidade))
            elif movimentacao.tipo_movimento == 'saida':
                saldo_anterior -= Decimal(str(movimentacao.quantidade))
        return saldo_anterior
    def saldo_atual(self):
        return self.saldo_anterior(datetime.now())
    
    def delete(self):
        """
        Remove a movimentação e reverte a alteração no estoque
        """
        # Reverter a movimentação no estoque
        if self.estoque:
            if self.tipo_movimento == 'entrada':
                self.estoque.quantidade -= self.quantidade
            elif self.tipo_movimento == 'saida':
                self.estoque.quantidade += self.quantidade
            elif self.tipo_movimento == 'ajuste':
                # No caso de ajuste, não fazer nada pois não temos a quantidade anterior
                pass
            
            # Garante que a quantidade nunca será negativa
            if self.estoque.quantidade < 0:
                self.estoque.quantidade = 0
                
            # Atualizar o estoque no banco de dados
            db.session.add(self.estoque)
        
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        """
        Representação em string da movimentação
        """
        return f'<MovimentacaoEstoque {self.tipo_movimento.upper()} - Qtd: {self.quantidade} - Data: {self.data_movimento}>'


class InventarioEstoque(db.Model):
    """
    Modelo para registrar inventários de estoque
    """
    __tablename__ = 'inventarios_estoque'
    
    id = db.Column(db.Integer, primary_key=True)
    data_inicio = db.Column(db.DateTime, default=datetime.now, nullable=False)
    data_fim = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='Em andamento', nullable=False)  # 'Em andamento', 'Concluído', 'Cancelado'
    tipo_inventario = db.Column(db.String(30), nullable=False)  # 'Geral', 'Parcial', 'Cíclico'
    observacoes = db.Column(db.Text)
    
    # Controle de auditoria
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    criado_por = db.relationship('Usuario', foreign_keys=[criado_por_id], backref='inventarios_criados')
    finalizado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    finalizado_por = db.relationship('Usuario', foreign_keys=[finalizado_por_id], backref='inventarios_finalizados')
    
    # Relacionamentos
    itens = db.relationship('ItemInventario', backref='inventario', cascade='all, delete-orphan')
    
    def save(self):
        """
        Salva o inventário no banco de dados
        """
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o inventário do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def finalizar(self, usuario_id):
        """
        Finaliza o inventário e ajusta o estoque com base nos itens contados
        """
        if self.status == 'Em andamento':
            self.status = 'Concluído'
            self.data_fim = datetime.now()
            self.finalizado_por_id = usuario_id
            
            # Ajustar o estoque para cada item do inventário
            for item in self.itens:
                if item.estoque:
                    # Criar movimentação de ajuste
                    movimento = MovimentacaoEstoque(
                        estoque_id=item.estoque_id,
                        tipo_movimento='ajuste',
                        quantidade=item.quantidade_contada,
                        observacao=f'Ajuste de inventário #{self.id}',
                        usuario_id=usuario_id,
                        origem_id=self.id,
                        origem_tipo='InventarioEstoque'
                    )
                    
                    # Atualizar a quantidade no estoque
                    diferenca = item.quantidade_contada - item.quantidade_sistema
                    item.diferenca = diferenca
                    item.estoque.quantidade = item.quantidade_contada
                    
                    db.session.add(movimento)
            
            db.session.commit()
            return True
        return False
    
    def __repr__(self):
        """
        Representação em string do inventário
        """
        return f'<InventarioEstoque #{self.id} - {self.status} - {self.data_inicio.strftime("%d/%m/%Y")}>'


class ItemInventario(db.Model):
    """
    Modelo para itens de inventário
    """
    __tablename__ = 'itens_inventario'
    
    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventarios_estoque.id', ondelete='CASCADE'), nullable=False)
    estoque_id = db.Column(db.Integer, db.ForeignKey('estoque.id'), nullable=False)
    estoque = db.relationship('Estoque', backref='itens_inventario')
    
    quantidade_sistema = db.Column(db.Numeric(15, 4), nullable=False)
    quantidade_contada = db.Column(db.Numeric(15, 4), nullable=True)
    diferenca = db.Column(db.Numeric(15, 4), nullable=True)
    observacoes = db.Column(db.Text)
    
    # Controle de auditoria
    contado_em = db.Column(db.DateTime, nullable=True)
    contado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    contado_por = db.relationship('Usuario', backref='itens_inventario_contados')
    
    def save(self):
        """
        Salva o item de inventário no banco de dados
        """
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def contar(self, quantidade, usuario_id, observacoes=None):
        """
        Registra a contagem do item
        """
        self.quantidade_contada = quantidade
        self.diferenca = quantidade - self.quantidade_sistema
        self.contado_em = datetime.now()
        self.contado_por_id = usuario_id
        
        if observacoes:
            self.observacoes = observacoes
            
        db.session.commit()
        return True
    
    def __repr__(self):
        """
        Representação em string do item de inventário
        """
        return f'<ItemInventario #{self.id} - Estoque: {self.estoque_id} - Sistema: {self.quantidade_sistema} - Contado: {self.quantidade_contada or "Não contado"}>' 