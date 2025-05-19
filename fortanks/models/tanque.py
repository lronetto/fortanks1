from datetime import datetime
from models.database import db

class Tanque(db.Model):
    """
    Modelo para representar tanques de projetos
    """
    __tablename__ = 'tanques'
    
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
    
    # Quantidades de placas
    placas_normais = db.Column(db.Integer, default=0)
    placas_fecho = db.Column(db.Integer, default=0)
    
    # Chave estrangeira para contrato
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    
    # Datas de controle
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    contrato = db.relationship('Contrato',back_populates='tanques',foreign_keys=[contrato_id])
    
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
    
    def before_save(self):
        """
        Verifica e configura campos antes de salvar
        """
        # Garantir que o campo UN sempre tenha um valor
        if not self.un:
            self.un = self.gerar_un()
    
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