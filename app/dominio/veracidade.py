"""Classificação de Veracidade de um Incidente (R9.4, R9.5).

A Veracidade expressa a confiabilidade de um Incidente a partir da quantidade
de Relatos associados a ele. Função pura, sem efeitos colaterais.
"""

# Valores de Veracidade ordenados do menor para o maior grau de confiabilidade.
# A ordem é usada para raciocinar sobre a monotonicidade da classificação.
VERACIDADE_BAIXA = "baixa"
VERACIDADE_MEDIA = "media"
VERACIDADE_ALTA = "alta"

# Ordem crescente de confiabilidade (R9.4): índice maior => Veracidade maior.
_ORDEM_VERACIDADE = (VERACIDADE_BAIXA, VERACIDADE_MEDIA, VERACIDADE_ALTA)


def veracidade(qtd_relatos: int) -> str:
    """Classifica a Veracidade de um Incidente pela quantidade de Relatos.

    Faixas (R9.5):
        - 1 ou 2 Relatos  -> "baixa"
        - 3 a 5 Relatos   -> "media"
        - 6 ou mais Relatos -> "alta"

    Monotonicidade (R9.4): aumentar ``qtd_relatos`` nunca reduz a Veracidade.

    Args:
        qtd_relatos: Quantidade de Relatos associados ao Incidente (>= 1).

    Returns:
        Uma das classificações: "baixa", "media" ou "alta".

    Raises:
        ValueError: Se ``qtd_relatos`` for menor que 1.
    """
    if qtd_relatos < 1:
        raise ValueError("qtd_relatos deve ser maior ou igual a 1")

    if qtd_relatos <= 2:
        return VERACIDADE_BAIXA
    if qtd_relatos <= 5:
        return VERACIDADE_MEDIA
    return VERACIDADE_ALTA
