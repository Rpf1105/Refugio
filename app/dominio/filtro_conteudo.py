"""Filtro de Conteúdo para Pedidos de Ajuda (R11.3–R11.5).

Detecta Termos Bloqueados (solicitações financeiras / golpes) na descrição de
um Pedido de Ajuda. A correspondência é insensível a maiúsculas/minúsculas e a
acentuação. Termos de palavra única usam limite de palavra (evita falsos
positivos como "despixado"); expressões compostas usam substring.

Todas as funções são puras.
"""

import re
import unicodedata

# Conjunto de Termos Bloqueados (R11.3). Mantidos já sem acentos; a comparação
# normaliza ambos os lados, então variações acentuadas na descrição são cobertas.
TERMOS_BLOQUEADOS = [
    "pix",
    "chave pix",
    "transferencia",
    "ted",
    "doc",
    "boleto",
    "cartao",
    "paypal",
    "dinheiro",
    "pagamento",
    "conta bancaria",
]


def normalizar(texto: str) -> str:
    """Normaliza o texto para comparação: minúsculas + remoção de acentos (NFD).

    Decompõe os caracteres na forma NFD e descarta os diacríticos (categoria
    Unicode "Mn"), devolvendo o texto em caixa baixa e sem acentos.
    """
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def contem_termo_bloqueado(descricao: str) -> bool:
    """Indica se a descrição contém ao menos um Termo Bloqueado (R11.4, R11.5).

    - Termos de palavra única são comparados com limite de palavra, para evitar
      falsos positivos em palavras que apenas contêm o termo (ex.: "despixado").
    - Expressões compostas (com espaço) são comparadas por substring.
    """
    norm = normalizar(descricao)
    for termo in TERMOS_BLOQUEADOS:
        termo_norm = normalizar(termo)
        if " " in termo_norm:
            if termo_norm in norm:
                return True
        else:
            if re.search(r"\b" + re.escape(termo_norm) + r"\b", norm):
                return True
    return False
