"""Cálculo da Rota Segura por grade (abordagem simplificada, R3).

Este módulo implementa a Rota Segura descrita na seção "Rota Segura —
Abordagem Simplificada" do design. Em vez de um motor de roteamento completo,
sobrepõe uma grade sobre a região do Município, bloqueia as células cujo centro
cai dentro de alguma Área Afetada e executa uma busca de caminho (A*) sobre as
células livres.

Todas as funções são **puras**: para as mesmas entradas produzem a mesma saída,
sem efeitos colaterais, o que facilita o teste e o property-based testing.

Convenções de coordenadas
-------------------------
- Um **ponto** é uma sequência ``[lat, lng]`` (latitude, longitude) em graus.
- Um **polígono** de Área Afetada é uma lista de pontos ``[[lat, lng], ...]``.
  O anel pode ou não repetir o primeiro ponto no final; ambos são tolerados.
- Uma **polyline** (a rota retornada) é uma lista de pontos ``[[lat, lng], ...]``
  da origem ao destino.

Garantia de correção (Property 12)
-----------------------------------
Quando uma rota é retornada, nenhum dos seus pontos (os centros das células do
caminho, além da origem e do destino) está contido em uma Área Afetada. Quando
não existe caminho livre, é levantada :class:`RotaSeguraNaoEncontradaError`.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

# Tipos de conveniência (apenas para legibilidade; não são validados em runtime).
Ponto = Sequence[float]
Poligono = Sequence[Ponto]

# Resolução padrão da grade: número de células por eixo (lat e lng).
# Um valor maior aumenta a precisão (contorna áreas com mais detalhe) ao custo
# de mais trabalho de busca. 60 é um compromisso razoável para o protótipo.
RESOLUCAO_PADRAO = 60

# Margem relativa aplicada à região da grade para garantir que origem, destino
# e áreas caibam com folga dentro dos limites, mesmo quando coincidem com a borda.
_MARGEM_RELATIVA = 0.05

# Mensagem padronizada exibida quando não há caminho livre (R3.3).
MENSAGEM_ROTA_NAO_ENCONTRADA = "nenhuma Rota Segura encontrada"


class RotaSeguraNaoEncontradaError(Exception):
    """Levantada quando não existe Rota Segura livre entre origem e destino.

    Sinaliza o caso descrito em R3.3: quando toda rota possível entre a origem
    e o destino seria bloqueada pelas Áreas Afetadas (ou quando a própria origem
    ou destino cai dentro de uma Área Afetada). A mensagem padrão é
    :data:`MENSAGEM_ROTA_NAO_ENCONTRADA`.
    """

    def __init__(self, mensagem: str = MENSAGEM_ROTA_NAO_ENCONTRADA) -> None:
        super().__init__(mensagem)


@dataclass(frozen=True)
class Grade:
    """Descrição imutável da grade sobreposta à região do Município.

    A grade cobre o retângulo ``[lat_min, lat_max] x [lng_min, lng_max]`` com
    ``linhas`` células no eixo da latitude e ``colunas`` células no eixo da
    longitude. O centro da célula ``(i, j)`` corresponde a um ponto geográfico
    via :meth:`centro`.

    Attributes:
        lat_min: Latitude mínima da região coberta.
        lat_max: Latitude máxima da região coberta.
        lng_min: Longitude mínima da região coberta.
        lng_max: Longitude máxima da região coberta.
        linhas: Número de células no eixo da latitude (>= 1).
        colunas: Número de células no eixo da longitude (>= 1).
    """

    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float
    linhas: int
    colunas: int

    @property
    def passo_lat(self) -> float:
        """Tamanho de uma célula no eixo da latitude, em graus."""
        return (self.lat_max - self.lat_min) / self.linhas

    @property
    def passo_lng(self) -> float:
        """Tamanho de uma célula no eixo da longitude, em graus."""
        return (self.lng_max - self.lng_min) / self.colunas

    def centro(self, i: int, j: int) -> tuple[float, float]:
        """Retorna o ponto ``(lat, lng)`` do centro da célula ``(i, j)``.

        Args:
            i: Índice da linha (0 .. ``linhas`` - 1), eixo da latitude.
            j: Índice da coluna (0 .. ``colunas`` - 1), eixo da longitude.

        Returns:
            Tupla ``(lat, lng)`` com as coordenadas do centro da célula.
        """
        lat = self.lat_min + (i + 0.5) * self.passo_lat
        lng = self.lng_min + (j + 0.5) * self.passo_lng
        return (lat, lng)

    def celula_de(self, lat: float, lng: float) -> tuple[int, int]:
        """Retorna a célula ``(i, j)`` que contém o ponto ``(lat, lng)``.

        O resultado é limitado (clamped) aos índices válidos da grade, de modo
        que pontos sobre a borda caiam na célula de borda mais próxima.

        Args:
            lat: Latitude do ponto, em graus.
            lng: Longitude do ponto, em graus.

        Returns:
            Tupla ``(i, j)`` com os índices de linha e coluna da célula.
        """
        i = int((lat - self.lat_min) / self.passo_lat)
        j = int((lng - self.lng_min) / self.passo_lng)
        i = min(self.linhas - 1, max(0, i))
        j = min(self.colunas - 1, max(0, j))
        return (i, j)


def ponto_em_poligono(lat: float, lng: float, poligono: Poligono) -> bool:
    """Testa se o ponto ``(lat, lng)`` está dentro de um polígono (ray casting).

    Implementa o algoritmo clássico de lançamento de raio (ray casting):
    conta quantas arestas do polígono um raio horizontal partindo do ponto
    cruza; um número ímpar de cruzamentos indica que o ponto está dentro.

    O polígono é interpretado como uma lista de vértices ``[lat, lng]``. O anel
    é fechado automaticamente (o último vértice é ligado ao primeiro), então
    repetir ou não o primeiro ponto no final é indiferente.

    É uma função pura. O comportamento exato sobre a fronteira não é garantido
    (um ponto exatamente sobre uma aresta pode ser classificado como dentro ou
    fora), o que é aceitável para o uso em grade do protótipo.

    Args:
        lat: Latitude do ponto a testar.
        lng: Longitude do ponto a testar.
        poligono: Lista de vértices ``[lat, lng]`` (anel). Menos de 3 vértices
            descreve uma área degenerada e resulta sempre em ``False``.

    Returns:
        ``True`` se o ponto está dentro do polígono, ``False`` caso contrário.
    """
    n = len(poligono)
    if n < 3:
        return False

    # x = longitude (eixo horizontal), y = latitude (eixo vertical).
    x = lng
    y = lat
    dentro = False

    j = n - 1
    for i in range(n):
        xi = poligono[i][1]
        yi = poligono[i][0]
        xj = poligono[j][1]
        yj = poligono[j][0]

        # A aresta (j -> i) cruza o raio horizontal em y se um vértice está
        # acima e o outro não, e o ponto de interseção está à direita de x.
        intersecta = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi) + xi
        )
        if intersecta:
            dentro = not dentro
        j = i

    return dentro


def _regiao_envolvente(
    origem: Ponto,
    destino: Ponto,
    areas: Iterable[Poligono],
) -> tuple[float, float, float, float]:
    """Calcula o retângulo que envolve origem, destino e as Áreas Afetadas.

    Aplica uma pequena margem relativa (:data:`_MARGEM_RELATIVA`) para garantir
    que todos os pontos relevantes caiam com folga dentro da grade, evitando
    efeitos de borda. Quando a extensão em um eixo é nula (todos os pontos
    colineares nesse eixo), usa uma margem absoluta mínima.

    Returns:
        Tupla ``(lat_min, lat_max, lng_min, lng_max)``.
    """
    lats = [origem[0], destino[0]]
    lngs = [origem[1], destino[1]]
    for poligono in areas:
        for p in poligono:
            lats.append(p[0])
            lngs.append(p[1])

    lat_min, lat_max = min(lats), max(lats)
    lng_min, lng_max = min(lngs), max(lngs)

    span_lat = lat_max - lat_min
    span_lng = lng_max - lng_min

    # Margem mínima absoluta para o caso de extensão nula em algum eixo.
    margem_lat = span_lat * _MARGEM_RELATIVA if span_lat > 0 else 0.001
    margem_lng = span_lng * _MARGEM_RELATIVA if span_lng > 0 else 0.001

    return (
        lat_min - margem_lat,
        lat_max + margem_lat,
        lng_min - margem_lng,
        lng_max + margem_lng,
    )


def construir_grade(
    origem: Ponto,
    destino: Ponto,
    areas: Iterable[Poligono],
    resolucao: int = RESOLUCAO_PADRAO,
) -> Grade:
    """Constrói a grade sobreposta à região que envolve os dados de entrada.

    A região é o retângulo que contém origem, destino e todos os vértices das
    Áreas Afetadas, acrescido de uma pequena margem. A grade recebe ``resolucao``
    células em cada eixo.

    Args:
        origem: Ponto de origem ``[lat, lng]``.
        destino: Ponto de destino ``[lat, lng]``.
        areas: Coleção de polígonos de Áreas Afetadas.
        resolucao: Número de células por eixo (>= 1). Padrão
            :data:`RESOLUCAO_PADRAO`.

    Returns:
        A :class:`Grade` resultante.

    Raises:
        ValueError: Se ``resolucao`` for menor que 1.
    """
    if resolucao < 1:
        raise ValueError("resolucao deve ser maior ou igual a 1")

    areas = list(areas)
    lat_min, lat_max, lng_min, lng_max = _regiao_envolvente(origem, destino, areas)
    return Grade(
        lat_min=lat_min,
        lat_max=lat_max,
        lng_min=lng_min,
        lng_max=lng_max,
        linhas=resolucao,
        colunas=resolucao,
    )


def _celulas_bloqueadas(grade: Grade, areas: Sequence[Poligono]) -> set[tuple[int, int]]:
    """Retorna o conjunto de células cujo centro cai dentro de alguma Área Afetada.

    Uma célula é considerada bloqueada se o seu centro geográfico está contido
    em pelo menos um polígono de Área Afetada (R3.1). É esse critério que
    sustenta a Property 12: o caminho só percorre centros de células livres.
    """
    bloqueadas: set[tuple[int, int]] = set()
    for i in range(grade.linhas):
        for j in range(grade.colunas):
            lat, lng = grade.centro(i, j)
            for poligono in areas:
                if ponto_em_poligono(lat, lng, poligono):
                    bloqueadas.add((i, j))
                    break
    return bloqueadas


# Vizinhança de 8 conexões (inclui diagonais) para permitir contornos suaves.
_VIZINHOS_8 = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
)


def _heuristica(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Heurística admissível para A*: distância euclidiana entre células."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _buscar_caminho_a_estrela(
    grade: Grade,
    bloqueadas: set[tuple[int, int]],
    inicio: tuple[int, int],
    fim: tuple[int, int],
) -> list[tuple[int, int]] | None:
    """Executa A* (8-conectividade) sobre as células livres da grade.

    Args:
        grade: A grade sobre a qual buscar.
        bloqueadas: Conjunto de células bloqueadas por Áreas Afetadas.
        inicio: Célula de origem ``(i, j)``.
        fim: Célula de destino ``(i, j)``.

    Returns:
        Lista de células ``(i, j)`` da origem ao destino (inclusive), ou
        ``None`` se não existe caminho livre.
    """
    if inicio in bloqueadas or fim in bloqueadas:
        return None
    if inicio == fim:
        return [inicio]

    # Fila de prioridade com (f = g + h, contador de desempate, célula).
    contador = 0
    aberta: list[tuple[float, int, tuple[int, int]]] = [
        (_heuristica(inicio, fim), contador, inicio)
    ]
    veio_de: dict[tuple[int, int], tuple[int, int]] = {}
    custo_g: dict[tuple[int, int], float] = {inicio: 0.0}
    fechados: set[tuple[int, int]] = set()

    while aberta:
        _, _, atual = heapq.heappop(aberta)
        if atual == fim:
            return _reconstruir(veio_de, atual)
        if atual in fechados:
            continue
        fechados.add(atual)

        i, j = atual
        for di, dj in _VIZINHOS_8:
            vizinho = (i + di, j + dj)
            vi, vj = vizinho
            if not (0 <= vi < grade.linhas and 0 <= vj < grade.colunas):
                continue
            if vizinho in bloqueadas or vizinho in fechados:
                continue
            # Impede "cortar quina" entre duas células bloqueadas na diagonal.
            if di != 0 and dj != 0:
                if (i + di, j) in bloqueadas and (i, j + dj) in bloqueadas:
                    continue
            passo = math.hypot(di, dj)
            novo_g = custo_g[atual] + passo
            if novo_g < custo_g.get(vizinho, math.inf):
                custo_g[vizinho] = novo_g
                veio_de[vizinho] = atual
                contador += 1
                f = novo_g + _heuristica(vizinho, fim)
                heapq.heappush(aberta, (f, contador, vizinho))

    return None


def _reconstruir(
    veio_de: dict[tuple[int, int], tuple[int, int]],
    atual: tuple[int, int],
) -> list[tuple[int, int]]:
    """Reconstrói o caminho a partir do mapa de predecessores do A*."""
    caminho = [atual]
    while atual in veio_de:
        atual = veio_de[atual]
        caminho.append(atual)
    caminho.reverse()
    return caminho


def calcular_rota_segura(
    origem: Ponto,
    destino: Ponto,
    areas: Iterable[Poligono],
    resolucao: int = RESOLUCAO_PADRAO,
) -> list[list[float]]:
    """Calcula uma Rota Segura entre ``origem`` e ``destino`` evitando Áreas Afetadas.

    Sobrepõe uma grade sobre a região que envolve origem, destino e as Áreas
    Afetadas; bloqueia as células cujo centro cai dentro de alguma área; e busca
    um caminho livre (A*, 8-conectividade) entre as células de origem e destino.
    O caminho é convertido em uma polyline ``[[lat, lng], ...]`` começando na
    origem informada e terminando no destino informado, com os centros das
    células livres percorridas entre eles (R3.1, R3.2).

    Garantia (Property 12): nenhum ponto da polyline retornada está contido em
    uma Área Afetada. Em particular, se a origem ou o destino cair dentro de uma
    Área Afetada, nenhuma rota é possível e o erro correspondente é levantado.

    Args:
        origem: Ponto de origem ``[lat, lng]``.
        destino: Ponto de destino ``[lat, lng]``.
        areas: Coleção de polígonos de Áreas Afetadas (cada um lista de
            ``[lat, lng]``). Pode ser vazia.
        resolucao: Número de células por eixo da grade (>= 1). Padrão
            :data:`RESOLUCAO_PADRAO`.

    Returns:
        A polyline da Rota Segura como ``[[lat, lng], ...]`` da origem ao destino.

    Raises:
        RotaSeguraNaoEncontradaError: Se não existe caminho livre entre origem e
            destino (R3.3), inclusive quando origem ou destino está dentro de uma
            Área Afetada.
        ValueError: Se ``resolucao`` for menor que 1.
    """
    areas = [list(poligono) for poligono in areas]

    # Origem/destino dentro de uma Área Afetada => nenhuma rota segura possível.
    for poligono in areas:
        if ponto_em_poligono(origem[0], origem[1], poligono):
            raise RotaSeguraNaoEncontradaError()
        if ponto_em_poligono(destino[0], destino[1], poligono):
            raise RotaSeguraNaoEncontradaError()

    grade = construir_grade(origem, destino, areas, resolucao)
    bloqueadas = _celulas_bloqueadas(grade, areas)

    inicio = grade.celula_de(origem[0], origem[1])
    fim = grade.celula_de(destino[0], destino[1])

    caminho_celulas = _buscar_caminho_a_estrela(grade, bloqueadas, inicio, fim)
    if caminho_celulas is None:
        raise RotaSeguraNaoEncontradaError()

    # Converte o caminho de células em polyline, ancorando nas coordenadas
    # exatas informadas de origem e destino e usando os centros das células
    # intermediárias (todas livres, logo fora de qualquer Área Afetada).
    polyline: list[list[float]] = [[float(origem[0]), float(origem[1])]]
    for celula in caminho_celulas[1:-1]:
        lat, lng = grade.centro(*celula)
        polyline.append([lat, lng])
    polyline.append([float(destino[0]), float(destino[1])])

    return polyline
