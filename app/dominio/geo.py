"""Funções puras de geolocalização do domínio.

Implementa o cálculo de distância entre duas coordenadas geográficas
(Cidadão → Abrigo, R2.4) usando a fórmula de Haversine.
"""

from __future__ import annotations

import math

# Raio médio da Terra em metros.
RAIO_TERRA_METROS = 6371000.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calcula a distância em metros entre dois pontos geográficos.

    Usa a fórmula de Haversine sobre uma esfera de raio médio da Terra
    (``RAIO_TERRA_METROS``). É uma função pura: para as mesmas entradas
    sempre produz a mesma saída, sem efeitos colaterais.

    Args:
        lat1: Latitude do primeiro ponto, em graus decimais.
        lng1: Longitude do primeiro ponto, em graus decimais.
        lat2: Latitude do segundo ponto, em graus decimais.
        lng2: Longitude do segundo ponto, em graus decimais.

    Returns:
        A distância em metros entre os dois pontos. O valor é sempre
        não-negativo, é zero quando as coordenadas são iguais e é
        simétrico em relação à ordem dos pontos.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    # Clamp numérico em [0, 1] para evitar erros de ponto flutuante em asin.
    c = 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))

    return RAIO_TERRA_METROS * c
