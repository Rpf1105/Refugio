"""Funções puras de domínio para o cálculo de gravidade de Incidentes.

Referência: design.md — seção "Algoritmos de Domínio".

O Nível_de_Gravidade é armazenado como as strings 'baixo', 'medio' e 'alto'
(sem acento em 'medio', conforme o enum do modelo de dados).
"""

# Valor_de_Gravidade de cada Nível_de_Gravidade (R9.2).
_VALORES = {
    "baixo": 1,
    "medio": 2,
    "alto": 3,
}


def valor_gravidade(nivel):
    """Converte um Nível_de_Gravidade no respectivo Valor_de_Gravidade.

    baixo -> 1, medio -> 2, alto -> 3 (R9.2).

    Levanta ``ValueError`` quando o nível é desconhecido.
    """
    try:
        return _VALORES[nivel]
    except KeyError:
        raise ValueError(
            f"nível de gravidade inválido: {nivel!r}; "
            f"valores válidos: {', '.join(_VALORES)}"
        )


def gravidade_media(relatos):
    """Calcula a Gravidade_Média de um Incidente (R9.3).

    ``relatos`` é uma lista não vazia de objetos que possuem o atributo
    ``nivel_gravidade`` (ex.: o modelo Relato). A Gravidade_Média é a média
    aritmética dos Valores_de_Gravidade dos relatos associados.

    Dado que cada Valor_de_Gravidade está em {1, 2, 3}, o resultado está
    sempre no intervalo [1.0, 3.0].

    Assume ``len(relatos) >= 1``; levanta ``ValueError`` caso contrário.
    """
    if not relatos:
        raise ValueError("gravidade_media requer ao menos um relato")

    soma = sum(valor_gravidade(r.nivel_gravidade) for r in relatos)
    return soma / len(relatos)
