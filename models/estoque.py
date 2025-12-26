from datetime import datetime
import json
import traceback
from models.database import db
from models.logs import Logs
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
    ProdComp_id = db.Column(db.Integer, db.ForeignKey('ProdComp.id'), nullable=True)
    produto_composto = db.relationship('ProdutoComposto', backref='estoque_items')
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
    def processar_movimentacoes(self,data_fim=None,data_inicio=None):
        """
        Processa as movimentações de estoque e atualiza a quantidade.
        Este método recalcula a quantidade baseado em todas as movimentações.
        """
        # Usar get_saldo_ate_data para garantir consistência
        if data_fim is None and data_inicio is None:
            # Se não há filtros, usar saldo real atual
            self.quantidade = self.get_saldo_real()
        else:
            # Se há filtros, processar movimentações no intervalo
            movimentacoes = MovimentacaoEstoque.query.filter_by(estoque_id = self.id)
            if data_inicio:
                movimentacoes = movimentacoes.filter(MovimentacaoEstoque.data_movimento >= data_inicio)
            if data_fim:
                movimentacoes = movimentacoes.filter(MovimentacaoEstoque.data_movimento < data_fim)
            movimentacoes = movimentacoes.order_by(MovimentacaoEstoque.data_movimento.asc()).all()
            self.quantidade = Decimal('0.0')
            for movimentacao in movimentacoes:
                if movimentacao.tipo_movimento == 'entrada':
                    self.quantidade += Decimal(str(movimentacao.quantidade))
                elif movimentacao.tipo_movimento == 'saida':
                    self.quantidade -= Decimal(str(movimentacao.quantidade))
                elif movimentacao.tipo_movimento == 'ajuste':
                    self.quantidade = Decimal(str(movimentacao.quantidade))
        self.save()
    def get_valor_unitario(self):
        """Retorna o valor unitário do item"""
        if self.material:
            return self.material.get_valor_unitario()
        elif self.produto_composto:
            return self.produto_composto.get_valor_total()
        return 0
    def get_estoque_atual(self):
        return self.get_saldo_ate_data()
    def get_estoque(self,data_fim=None,data_inicio=None):
        query = MovimentacaoEstoque.query.filter_by(estoque_id = self.id)
        if data_inicio:
            query = query.filter(MovimentacaoEstoque.data_movimento >= data_inicio)
        if data_fim is None:
            data_fim = datetime.now()
        query = query.filter(MovimentacaoEstoque.data_movimento < data_fim)
        return query.order_by(MovimentacaoEstoque.data_movimento.asc()).all()
    
    def get_saldo_ate_data(self, data_fim=None):
        """
        Calcula o saldo do estoque até uma data específica baseado nas movimentações
        """
        if data_fim is None:
            data_fim = datetime.now()
        
        # Adicionar um dia e definir hora como 23:59:59 para incluir todo o dia
        from datetime import timedelta
        if isinstance(data_fim, datetime):
            data_fim_completa = data_fim.replace(hour=23, minute=59, second=59)
        else:
            # Se for date, converter para datetime
            data_fim_completa = datetime.combine(data_fim, datetime.max.time())
        
        movimentacoes = self.get_estoque(data_fim=data_fim_completa)
        saldo = Decimal('0.0')
        
        for movimentacao in movimentacoes:
            if movimentacao.tipo_movimento == 'entrada':
                saldo += Decimal(str(movimentacao.quantidade))
            elif movimentacao.tipo_movimento == 'saida':
                saldo -= Decimal(str(movimentacao.quantidade))
            elif movimentacao.tipo_movimento == 'ajuste':
                # Para ajuste, a quantidade representa o novo saldo total
                saldo = Decimal(str(movimentacao.quantidade))
        
        return saldo
    
    def get_saldo_real(self, data_fim=None):
        """
        Calcula o saldo real baseado em todas as movimentações até uma data específica.
        Considera entradas, saídas e ajustes.
        Este método é um alias para get_saldo_ate_data() para manter compatibilidade.
        
        Args:
            data_fim (datetime, optional): Data limite para cálculo. Se None, usa datetime.now()
            
        Returns:
            Decimal: Saldo real calculado
        """
        return self.get_saldo_ate_data(data_fim)
    
    def sincronizar_quantidade(self):
        """
        Sincroniza a quantidade do estoque com o saldo real calculado a partir das movimentações.
        Use este método para corrigir inconsistências entre quantidade e saldo real.
        """
        saldo_real = self.get_saldo_real()
        if self.quantidade != saldo_real:
            print(f"Sincronizando estoque ID {self.id}: quantidade atual {self.quantidade} -> saldo real {saldo_real}")
            self.quantidade = saldo_real
            self.save()
            return True
        return False
    
    @classmethod
    def sincronizar_todos_estoques(cls):
        """
        Sincroniza a quantidade de todos os estoques com seus saldos reais.
        Útil para corrigir inconsistências em massa.
        """
        estoques = cls.query.all()
        sincronizados = 0
        for estoque in estoques:
            if estoque.sincronizar_quantidade():
                sincronizados += 1
        return sincronizados
    
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
    def to_dict(self):
        return {
            'id': self.id,
            'estoque_id': self.estoque_id,
            'tipo_movimento': self.tipo_movimento,
            'quantidade': self.quantidade,
            'data_movimento': self.data_movimento,
            'origem_id': self.origem_id,
            'origem_tipo': self.origem_tipo,
            'observacao': self.observacao,
            'usuario_id': self.usuario_id,
        }
    @classmethod
    def get_historico_saldo_para_grafico(cls, estoque_id, data_inicio=None, data_fim=None, agrupar_por_semana=False):
        """
        Retorna o histórico de saldo para um item de estoque específico,
        calculado a partir de suas movimentações.

        Args:
            estoque_id (int): ID do item de estoque.
            data_inicio (datetime.date, optional): Data de início do período.
            data_fim (datetime.date, optional): Data de fim do período.
            agrupar_por_semana (bool): Se True, agrupa os dados por semana.

        Returns:
            list: Lista de dicionários {"data": data_formatada, "saldo": saldo_acumulado}
        """
        # Buscar o item de estoque para obter a quantidade atual
        estoque = Estoque.query.get(estoque_id)
        if not estoque:
            return []
        
        query = cls.query.filter_by(estoque_id=estoque_id)

        # Calcular saldo inicial (antes da data_inicio, se houver)
        saldo_inicial = Decimal('0.0')
        if data_inicio:
            # Buscar todas as movimentações antes da data de início
            movimentacoes_anteriores = cls.query.filter_by(estoque_id=estoque_id).filter(
                MovimentacaoEstoque.data_movimento < data_inicio
            ).order_by(MovimentacaoEstoque.data_movimento.asc()).all()
            
            for mov in movimentacoes_anteriores:
                if mov.tipo_movimento == 'entrada':
                    saldo_inicial += mov.quantidade
                elif mov.tipo_movimento == 'saida':
                    saldo_inicial -= mov.quantidade
                elif mov.tipo_movimento == 'ajuste':
                    saldo_inicial = mov.quantidade
            
            query = query.filter(MovimentacaoEstoque.data_movimento >= data_inicio)
        
        # Importar datetime e timedelta para uso no método
        from datetime import datetime, timedelta
        
        if data_fim:
            # Adicionar um dia para incluir movimentações no dia final
            query = query.filter(MovimentacaoEstoque.data_movimento < data_fim + timedelta(days=1))

        movimentacoes = query.order_by(MovimentacaoEstoque.data_movimento.asc()).all()

        historico_saldo = []
        saldo_acumulado = saldo_inicial  # Inicia com saldo anterior à data_inicio, se houver

        for mov in movimentacoes:
            if mov.tipo_movimento == 'entrada':
                saldo_acumulado += mov.quantidade
            elif mov.tipo_movimento == 'saida':
                saldo_acumulado -= mov.quantidade
            elif mov.tipo_movimento == 'ajuste':
                saldo_acumulado = mov.quantidade

            # Formatar a data para string (ex: YYYY-MM-DD HH:MM:SS) para o Plotly
            historico_saldo.append({
                "data": mov.data_movimento.strftime('%Y-%m-%d %H:%M:%S'),
                "saldo": float(saldo_acumulado) # Plotly geralmente prefere float
            })
        
        # Se não há filtro de data_fim, verificar se há movimentações após a última data do histórico
        if not data_fim and historico_saldo:
            # Buscar a última data do histórico
            ultima_data_str = historico_saldo[-1]['data']
            if ' ' in ultima_data_str:
                ultima_data = datetime.strptime(ultima_data_str, '%Y-%m-%d %H:%M:%S')
            else:
                ultima_data = datetime.strptime(ultima_data_str, '%Y-%m-%d')
            
            # Verificar se há movimentações após a última data do histórico
            movimentacoes_posteriores = cls.query.filter_by(estoque_id=estoque_id).filter(
                MovimentacaoEstoque.data_movimento > ultima_data
            ).order_by(MovimentacaoEstoque.data_movimento.asc()).all()
            
            # Se houver movimentações posteriores, processá-las
            if movimentacoes_posteriores:
                saldo_atual = historico_saldo[-1]['saldo']
                for mov in movimentacoes_posteriores:
                    if mov.tipo_movimento == 'entrada':
                        saldo_atual += mov.quantidade
                    elif mov.tipo_movimento == 'saida':
                        saldo_atual -= mov.quantidade
                    elif mov.tipo_movimento == 'ajuste':
                        saldo_atual = mov.quantidade
                    
                    historico_saldo.append({
                        "data": mov.data_movimento.strftime('%Y-%m-%d %H:%M:%S'),
                        "saldo": float(saldo_atual)
                    })
            
            # Verificar se o saldo calculado corresponde ao saldo real atual
            # Usar get_saldo_real() em vez de estoque.quantidade
            saldo_calculado = historico_saldo[-1]['saldo']
            saldo_real_atual = estoque.get_saldo_real()
            diferenca = abs(float(saldo_real_atual) - saldo_calculado)
            
            # Se a diferença for muito grande (> 1%), pode indicar um problema
            # Mas não vamos adicionar um ponto artificial - deixamos o gráfico mostrar o histórico real
            if diferenca > 0.01 and not movimentacoes_posteriores:
                # Log para debug, mas não adiciona ponto artificial
                print(f"AVISO: Diferença entre saldo calculado ({saldo_calculado}) e saldo real atual ({saldo_real_atual})")
        
        # Se não há histórico e não há filtro de data_fim, criar um ponto inicial apenas se não houver movimentações
        elif not data_fim and not historico_saldo:
            # Verificar se realmente não há movimentações
            total_movimentacoes = cls.query.filter_by(estoque_id=estoque_id).count()
            if total_movimentacoes == 0:
                # Se não há movimentações, criar um ponto inicial com o saldo real atual
                agora = datetime.now()
                saldo_real = estoque.get_saldo_real()
                historico_saldo.append({
                    "data": agora.strftime('%Y-%m-%d %H:%M:%S'),
                    "saldo": float(saldo_real)
                })
        
        # Se solicitado, agrupar por semana
        if agrupar_por_semana and historico_saldo:
            historico_saldo = cls._agrupar_por_semana(historico_saldo)
            # Não adicionar ponto artificial após agrupamento - o agrupamento já processou todas as movimentações
        
        return historico_saldo
    
    @classmethod
    def _agrupar_por_semana(cls, historico_saldo):
        """
        Agrupa o histórico de saldo por semana, usando o último valor de cada semana.
        
        Args:
            historico_saldo: Lista de dicionários com "data" e "saldo"
            
        Returns:
            list: Lista agrupada por semana
        """
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        # Agrupar por semana (ano-semana)
        semanas = defaultdict(list)
        
        for item in historico_saldo:
            data_str = item['data']
            # Converter string para datetime
            if ' ' in data_str:
                data_dt = datetime.strptime(data_str, '%Y-%m-%d %H:%M:%S')
            else:
                data_dt = datetime.strptime(data_str, '%Y-%m-%d')
            
            # Calcular ano e número da semana (ISO week)
            ano, semana, dia_semana = data_dt.isocalendar()
            chave_semana = f"{ano}-W{semana:02d}"
            
            semanas[chave_semana].append({
                'data': data_dt,
                'saldo': item['saldo']
            })
        
        # Para cada semana, pegar o último valor (mais recente)
        historico_agrupado = []
        for chave_semana in sorted(semanas.keys()):
            itens_semana = semanas[chave_semana]
            # Ordenar por data para pegar o último
            itens_semana.sort(key=lambda x: x['data'])
            ultimo_item = itens_semana[-1]
            
            # Calcular início da semana (segunda-feira)
            # weekday() retorna: 0=segunda, 1=terça, ..., 6=domingo
            data_dt = ultimo_item['data']
            dias_para_segunda = data_dt.weekday()  # 0 para segunda, 6 para domingo
            inicio_semana = data_dt - timedelta(days=dias_para_segunda)
            
            # Formatar como "Semana de DD/MM/YYYY"
            historico_agrupado.append({
                "data": inicio_semana.strftime('%Y-%m-%d %H:%M:%S'),
                "saldo": ultimo_item['saldo'],
                "semana": f"Semana de {inicio_semana.strftime('%d/%m/%Y')}"
            })
        
        return historico_agrupado
    
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
            
            # Permitir estoque negativo - removida verificação de disponibilidade
            # if estoque.quantidade < quantidade:
            #     print(f"Erro: Quantidade em estoque insuficiente: {estoque.quantidade} < {quantidade}")
            #     raise ValueError(f"Quantidade insuficiente em estoque. Disponível: {estoque.quantidade}, Necessário: {quantidade}")
                
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
    
    def remover(self,quantidade,estoque_id,origem_id,origem_tipo,usuario_id,motivo=None,log=False):
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

    def Ajuste(self,quantidade,estoque_id,origem_id,origem_tipo,usuario_id,data_movimento=None):
        """
        Cria uma nova movimentação de estoque
        """
        estoque = Estoque.query.get(estoque_id)
        if not estoque:
            raise ValueError(f"Estoque ID {estoque_id} não encontrado")
        if not data_movimento:
            data_movimento = datetime.now()
        diferenca = quantidade - estoque.get_saldo_ate_data(data_fim=data_movimento)
        tipo_movimento = 'ajuste'
        self.quantidade = quantidade
        self.estoque_id = estoque_id
        self.usuario_id = usuario_id
        self.origem_id = origem_id
        self.origem_tipo = origem_tipo
        self.observacao = f'Ajuste de estoque #{origem_tipo} #{origem_id}'
        self.data_movimento = data_movimento
        self.tipo_movimento = tipo_movimento

    def save(self,log=False):
        """
        Salva a movimentação de estoque e atualiza o estoque
        """
        import traceback
        
        try:
            if log:
                print(f"Iniciando save() de MovimentacaoEstoque: tipo={self.tipo_movimento}, quantidade={self.quantidade}, estoque_id={self.estoque_id}")
            if self.estoque_id:
                self.estoque = Estoque.query.get(self.estoque_id)
            # Atualizar quantidade do estoque baseado no tipo de movimento
            if self.estoque:
                estoque_anterior = self.estoque.quantidade
            
                if self.tipo_movimento == 'entrada':
                    self.estoque.quantidade += self.quantidade
                    if log:
                        print(f"Movimentação ENTRADA: {estoque_anterior} + {self.quantidade} = {self.estoque.quantidade}")
                    
                elif self.tipo_movimento == 'saida':
                    # Permitir estoque negativo - removida verificação de quantidade suficiente
                    self.estoque.quantidade -= self.quantidade
                    if log:
                        print(f"Movimentação SAÍDA: {estoque_anterior} - {self.quantidade} = {self.estoque.quantidade}")
                    if self.estoque.quantidade < 0:
                        if log:
                            print(f"AVISO: Estoque ficou negativo: {self.estoque.quantidade}")
                
                elif self.tipo_movimento == 'ajuste':
                    if log:
                        print(f"Movimentação AJUSTE: {estoque_anterior} -> {self.quantidade}")
                    # Para ajuste, a quantidade já é o novo saldo total
                    # Recalcular a partir de todas as movimentações para garantir consistência
                    self.estoque.quantidade = self.estoque.get_saldo_real()
                
                # Permitir estoque negativo - removida correção que forçava para 0
                # if self.estoque.quantidade < 0:
                #     print(f"AVISO: Quantidade negativa corrigida para 0")
                #     self.estoque.quantidade = 0
                # Importante: atualizar o estoque no banco de dados
                db.session.add(self.estoque)
            else:
                if log:
                    print(f"ERRO: Estoque não encontrado para ID {self.estoque_id}")
        
        # Adiciona a movimentação ao banco
            if not self.id:  # Se for um novo registro
                db.session.add(self)
            
                # Executa o commit para salvar as alterações
                db.session.flush()  # Garante que os objetos tenham IDs
                if log:
                    print(f"Movimentação de estoque criada com ID {self.id}")
                
                db.session.commit()
                if log:
                    print(f"Transação concluída com sucesso")
                return True
            
        except Exception as e:
            db.session.rollback()
            if log:
                print(f"ERRO ao salvar movimentação de estoque: {str(e)}")
            print(traceback.format_exc())
            raise e

    def saldo_anterior(self, data_movimento=None):
        """
        Calcula o saldo anterior a uma data específica.
        Considera entradas, saídas e ajustes.
        """
        if data_movimento is None:
            data_movimento = self.data_movimento
        
        # Se não há estoque associado, retornar 0
        if not self.estoque:
            return Decimal('0.0')
        
        # Se não há data_movimento, retornar saldo atual
        if data_movimento is None:
            return self.estoque.get_saldo_real()
        
        # Calcular saldo até um momento antes da data especificada
        from datetime import timedelta
        data_anterior = data_movimento - timedelta(microseconds=1)
        return self.estoque.get_saldo_real(data_anterior)
    
    def saldo_atual(self):
        """
        Calcula o saldo atual baseado em todas as movimentações.
        Usa get_saldo_real() do estoque associado.
        """
        if not self.estoque:
            return Decimal('0.0')
        return self.estoque.get_saldo_real()
    
    def delete(self):
        """
        Remove a movimentação e reverte a alteração no estoque
        """
        try:
            # Reverter a movimentação no estoque
            if self.estoque:
                if self.tipo_movimento == 'entrada':
                    self.estoque.quantidade -= self.quantidade
                elif self.tipo_movimento == 'saida':
                    self.estoque.quantidade += self.quantidade
                elif self.tipo_movimento == 'ajuste':
                    # No caso de ajuste, não fazer nada pois não temos a quantidade anterior
                    pass
                
                # Permitir estoque negativo - removida correção que forçava para 0
                # if self.estoque.quantidade < 0:
                #     self.estoque.quantidade = 0
                    
                # Atualizar o estoque no banco de dados
                db.session.add(self.estoque)

                log = {
                    'MovimentacaoEstoque deletada': self.id,
                    'movimentacao': self.to_dict(),
                }
                Logs(local='estoque', data=datetime.now(), texto=json.dumps(log))
        except Exception as e:
            print(f"ERRO ao deletar movimentação de estoque: {str(e)}")
            print(traceback.format_exc())
            raise e
            return False
        finally:
            db.session.delete(self)
            db.session.commit()
            print(f"Movimentação de estoque deletada com sucesso")
            return True
    
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
                  mov=MovimentacaoEstoque()
                  mov.Ajuste(item.quantidade_contada,item.estoque_id,self.id,"InventarioEstoque",usuario_id,item.contado_em)
                  mov.save()
            self.save()
            return True
        return False
    
    def cancelar(self, usuario_id):
        """
        Cancela o inventário e desfaz movimentações se o inventário estiver concluído
        """
        if self.status not in ['Em andamento', 'Concluído']:
            return False

        if self.status == 'Concluído':
            # Desfazer movimentações criadas na finalização
            movimentacoes = MovimentacaoEstoque.query.filter_by(
                origem_tipo='InventarioEstoque',
                origem_id=self.id
            ).all()
            itens_por_estoque = {item.estoque_id: item for item in self.itens}

            for movimento in movimentacoes:
                item_ref = itens_por_estoque.get(movimento.estoque_id)
                if movimento.estoque and item_ref:
                    movimento.estoque.quantidade = item_ref.quantidade_sistema
                    db.session.add(movimento.estoque)
                db.session.delete(movimento)

        self.status = 'Cancelado'
        self.data_fim = datetime.now()
        self.finalizado_por_id = usuario_id

        db.session.commit()
        return True

    def reabrir(self, usuario_id):
        """
        Reabre um inventário concluído ou cancelado, desfazendo ajustes e retornando para 'Em andamento'
        """
        if self.status not in ['Concluído', 'Cancelado']:
            return False

        # Se o inventário estava concluído, desfazer movimentações de ajuste criadas na finalização
        if self.status == 'Concluído':
            movimentacoes = MovimentacaoEstoque.query.filter_by(
                origem_tipo='InventarioEstoque',
                origem_id=self.id
            ).all()
            itens_por_estoque = {item.estoque_id: item for item in self.itens}

            for movimento in movimentacoes:
                item_ref = itens_por_estoque.get(movimento.estoque_id)
                if movimento.estoque and item_ref:
                    movimento.estoque.quantidade = item_ref.quantidade_sistema
                    db.session.add(movimento.estoque)
                db.session.delete(movimento)

        # Voltar para status em andamento para permitir nova contagem
        self.status = 'Em andamento'
        self.data_fim = None
        self.finalizado_por_id = None

        db.session.commit()
        return True
    
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
    
    def contar(self, quantidade, usuario_id, observacoes=None, data_contagem=None):
        """
        Registra a contagem do item
        """
        self.quantidade_contada = quantidade
        self.diferenca = quantidade - self.quantidade_sistema
        self.contado_em = data_contagem if data_contagem else datetime.now()
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