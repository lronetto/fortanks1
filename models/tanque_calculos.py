from models.database import db
from models.tanque import Tanque
import math

class TanqueCalculos():
    _volume_util = 0
    _area_base = 0
    _placas_real=0
    _placas=0
    _diametro_projeto = 0
    _diametro_calculado = 0
    _comprimento_calculado = 0
    _arredondamento = 0
    #arredondamento = 0 para cima, 1 para baixo
    # sistema = 1 SC-10, sistema = 2 SC-14, sistema = 3 SR-06
    _sistema = 0
    def __init__(self):

        self.tanque = tanque

    def calcular_sistema(self):
        if self.tanque.altura_total > 10:
            self._sistema = 2
        elif self.tanque.altura_total <= 10:
            self._sistema = 1
        elif self.tanque.altura_total <= 6:
            self._sistema = 3

    def calcular_placas_real(self):
        if self._sistema == 1:
            self.placas_real = (math.pi * (self._diametro_projeto + 0.24))/2
        elif self._sistema == 2:
            self.placas_real = (math.pi * (self._diametro_projeto + 0.3))/2
        elif self._sistema == 3:
            self.placas_real = (math.pi * (self._diametro_projeto + 0.09))/2

    def calcular_placas(self,_arredondamento):
        if _arredondamento == 0:
            self.placas = math.ceil(self.placas_real)
        elif _arredondamento == 1:
            self.placas = math.floor(self.placas_real)
    def calcular_diametro_calculado(self):
        #diametro interno no meio do painel
        if self._sistema == 1:
            self._diametro_calculado = (1.205/math.tan(math.pi/self.placas)-0.24)*2
        elif self._sistema == 2:
            self._diametro_calculado = (1.205/math.tan(math.pi/self.placas)-0.295)*2
        elif self._sistema == 3:
            self._diametro_calculado = (((2.1+0.006-0.005)/2)/math.tan(math.pi/self.placas)-0.07)*2
    def calcular_volume_util(self):
        return self.tanque.volume_util

    def calcular_volume_total(self):
        return self.tanque.volume_total