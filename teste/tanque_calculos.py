import math

indices = {
    "SC14_PNVOLM": 0.607,
    "SC14_PFVOLM": 0.796, 
    "SC10_PNVOLM": 0.796,
    "SC10_PFVOLM": 0.796,
    "SR06_VOLM": 0.796,
}
class Placa():
    sistema = 0
    ht = 0
    hu = 0
    #tipo = 0 PN, 1 PF
    tipo = 0
    peso = 0
    volume = 0

    def calculo_peso(self):
        if self.sistema == 1:
            pesopm = indices["SC10_VOLM"]*2.5
            self._peso = self._volume_util*indices["SC10_VOLM"]
        elif self.sistema == 2:
            pesopm = indices["SC14_VOLM"]*2.5
            self._peso = self._volume_util*indices["SC14_VOLM"]
        elif self.sistema == 3:
            self._peso = self._volume_util*indices["SR06_VOLM"]
class Tanque():
    nplacaspn = 0
    nplacaspf = 0
class TanqueOrcamento():
class TanqueCalculos():
    sistema = 0
    ht = 0
    hu = 0
    arredondamento = 0
    D_projeto = 0
    D_ajustado = 0
    
    
    def __init__(self,diametro_projeto,altura_total,altura_util,arredondamento,sistema=0):
        self._diametro_projeto = diametro_projeto
        self._altura_total = altura_total
        self._altura_util = altura_util
        self._arredondamento = arredondamento
        self.calcular_sistema()
        self.calcular_placas_real()
        self.calcular_placas()
        self.calcular_diametro_calculado()
        self.calcular_volumes()
        self.calcular_volume_projeto()
        self.print_results()

    def print_results(self):
        print(f"Diametro Projeto: {self._diametro_projeto}")
        print(f"Altura Total: {self._altura_total}")
        print(f"Altura Util: {self._altura_util}")
        print(f"Arredondamento: {self._arredondamento}")
        print(f"Sistema: {self._sistema}")
        print(f"Placas Real: {self._placas_real}")
        print(f"Placas: {self._nplacas}")
        print(f"Diametro Calculado: {self._diametro_calculado}")
        print(f"Area Base: {self._area_base}")
        print(f"Volume Util: {self._volume_util}")
        print(f"Volume Projeto: {self._volume_projeto}")


    def calcular_sistema(self):

        if self._altura_total > 10:
            self._sistema = 2
        elif self._altura_total <= 10:
            self._sistema = 1
        elif self._altura_total <= 6:
            self._sistema = 3
     # sistema = 1 SC-10, sistema = 2 SC-14, sistema = 3 SR-06
    def calcular_placas_real(self):
        if self._sistema == 1:
            self._placas_real = math.pi * ((self._diametro_projeto + 0.24)/2.4)
        elif self._sistema == 2:
            self._placas_real = math.pi * ((self._diametro_projeto + 0.3)/2.4)
        elif self._sistema == 3:
            self._placas_real = math.pi * ((self._diametro_projeto + 0.09)/2.4)

    def calcular_placas(self):
        if self._arredondamento == 0:
            self._nplacas = math.ceil(self._placas_real)
        elif self._arredondamento == 1:
            self._nplacas = math.floor(self._placas_real)
        self._nplacasFecho = self._nplacas/40
        self._nplacasNormais = self._nplacas-self._nplacasFecho
    def calcular_diametro_calculado(self):
        #diametro interno no meio do painel
        if self._sistema == 1:
            self._diametro_calculado = (1.205/math.tan(math.pi/self._nplacas)-0.24)*2
        elif self._sistema == 2:
            self._diametro_calculado = (1.205/math.tan(math.pi/self._nplacas)-0.295)*2
        elif self._sistema == 3:
            self._diametro_calculado = (((2.1+0.006-0.005)/2)/math.tan(math.pi/self._nplacas)-0.07)*2
    def calcular_volumes(self):
        if self._sistema == 1:
            RaioJunta = 1.205/math.sin(math.pi/self._nplacas)-0.24
            RaioCentro = RaioJunta*math.cos(math.pi/self._nplacas)
        elif self._sistema == 2:
            RaioJunta = 1.205/math.sin(math.pi/self._nplacas)-0.3
            RaioCentro = RaioJunta*math.cos(math.pi/self._nplacas)
        elif self._sistema == 3:
            RaioJunta = ((2.1+0.006-0.005)/2)/math.sin(math.pi/self._nplacas)-0.07
            RaioCentro = RaioJunta*math.cos(math.pi/self._nplacas)

        d = RaioCentro*2*math.tan(math.pi/self._nplacas)
        self._area_base = self._nplacas*d*RaioCentro/2
        self._volume_util = self._area_base*self._altura_util

    def calcular_volume_projeto(self):
        self._volume_projeto = math.pi * ((self._diametro_projeto/2)**2) * self._altura_util
    

def main():
    calculos = TanqueCalculos(16.7,5,5,0)
if __name__ == "__main__":
    main()