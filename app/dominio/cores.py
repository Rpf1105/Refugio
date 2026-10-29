"""Mapeamento de cores de gravidade do domínio Refúgio.

Funções puras que traduzem gravidade (média numérica ou nível textual) para a
Cor_de_Gravidade correspondente, usando os tokens do Sistema de Design.

- Amarelo (gravidade baixa):  #F2C94C
- Laranja (gravidade média):  #E8A028
- Vermelho (gravidade alta):  #C9291C

Referências de design:
- Mapeamento Gravidade Média → Cor (R12.4)
- Cor por Nível (R12.1–R12.3)
"""

# Tokens de cor do Sistema de Design (hex strings).
AMARELO = "#F2C94C"
LARANJA = "#E8A028"
VERMELHO = "#C9291C"

# Níveis de gravidade válidos.
NIVEL_BAIXO = "baixo"
NIVEL_MEDIO = "medio"
NIVEL_ALTO = "alto"

_CORES_POR_NIVEL = {
    NIVEL_BAIXO: AMARELO,
    NIVEL_MEDIO: LARANJA,
    NIVEL_ALTO: VERMELHO,
}


def cor_por_media(media: float) -> str:
    """Mapeia a Gravidade_Média para a Cor_de_Gravidade correspondente (R12.4).

    Faixas (média esperada em [1.0, 3.0]):
        - amarelo:  1.0 <= media <= 1.5
        - laranja:  1.5 <  media <= 2.5
        - vermelho: 2.5 <  media <= 3.0

    Args:
        media: Gravidade média do Incidente, em [1.0, 3.0].

    Returns:
        A cor (hex string) correspondente à faixa da média.

    Raises:
        ValueError: se ``media`` estiver fora de [1.0, 3.0].
    """
    if not 1.0 <= media <= 3.0:
        raise ValueError("a gravidade média deve estar em [1.0, 3.0]")
    if media <= 1.5:
        return AMARELO
    if media <= 2.5:
        return LARANJA
    return VERMELHO


def cor_por_nivel(nivel: str) -> str:
    """Mapeia um Nível_de_Gravidade individual para a Cor_de_Gravidade (R12.1–R12.3).

    Args:
        nivel: Um dos valores 'baixo', 'medio' ou 'alto'.

    Returns:
        A cor (hex string) correspondente ao nível.

    Raises:
        ValueError: se ``nivel`` não for um nível de gravidade válido.
    """
    try:
        return _CORES_POR_NIVEL[nivel]
    except KeyError:
        validos = ", ".join(_CORES_POR_NIVEL)
        raise ValueError(f"nível de gravidade inválido: {nivel!r} (válidos: {validos})")
