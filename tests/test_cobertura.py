"""Janela comparavel: onde a fonte passa a cobrir cada produto.

O caso real que motivou o modulo (artefato de 2026-11-05): o Diesel B vai de
46 mil m3 em dez/2009 para 3.037 em mar/2010 -- a fonte da ANP so passa a
trazer diesel em 2010, e o diesel e metade do mercado. Somar 2007-2009 com
2010+ mostra um mercado triplicando por artefato de cobertura.

Os testes travam os dois lados: detectar a entrada de cobertura E nao acusar
queda secular real (o Oleo Comb. cai 80% em 18 anos, de verdade).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import cobertura  # noqa: E402

# 237 meses, a mesma extensao da serie real (2007-01 a 2026-09): o limite de
# "degrau no inicio" e proporcional, entao testar com serie curta mediria
# outra coisa.
MESES = [f"{a}-{m:02d}" for a in range(2007, 2027) for m in range(1, 13)][:237]


def agg_de(series: dict, meses=None) -> dict:
    """{produto: [volume por mes]} -> cubo agregado."""
    meses = meses or MESES
    return {(mes, "AGENTE", "SP", "TRR", prod): v
            for prod, serie in series.items()
            for mes, v in zip(meses, serie, strict=True) if v}


# --- entrada de cobertura ---------------------------------------------------

def test_detecta_entrada_de_cobertura():
    """36 meses quase nulos, depois nivel normal: o degrau do diesel.

    O inicio sai em 37, nao em 36: a regra pega o ULTIMO indice que satisfaz o
    degrau, e a tolerancia de 10% ainda aceita uma janela com um mes posterior
    a entrada (1.011 contra 12.000 = 8,4%). O vies e de um mes, sempre para o
    lado de descartar dado -- que e o lado certo para errar aqui, e e o que
    acertou o caso real: o diesel entra em jan/2010 com 244 mil m3 e fev com
    1.915, ambos rampa, e a regra comeca a serie em mar/2010, o primeiro mes
    de nivel normal (3.037).
    """
    serie = [1.0] * 36 + [3000.0] * (len(MESES) - 36)
    r = cobertura.analisar(agg_de({"Diesel B": serie}), MESES)
    assert r["por_produto"]["Diesel B"]["inicio"] == MESES[37]
    assert r["inicio_comparavel"] == MESES[37]
    assert r["por_produto"]["Diesel B"]["razao"] < cobertura.RAZAO_DEGRAU


def test_inicio_comparavel_e_o_mais_tardio_entre_produtos():
    """Somar os produtos so e legitimo onde TODOS estao cobertos."""
    r = cobertura.analisar(agg_de({
        "A": [1.0] * 12 + [1000.0] * (len(MESES) - 12),
        "B": [1.0] * 36 + [1000.0] * (len(MESES) - 36),
        "C": [1000.0] * len(MESES),
    }), MESES)
    assert r["inicio_comparavel"] == MESES[37]


def test_serie_inteira_coberta_comeca_no_primeiro_mes():
    r = cobertura.analisar(agg_de({"Gasolina C": [1600.0] * len(MESES)}), MESES)
    assert r["por_produto"]["Gasolina C"]["inicio"] == MESES[0]
    assert "razao" not in r["por_produto"]["Gasolina C"]


# --- o que NAO pode ser acusado ---------------------------------------------

def test_queda_secular_real_nao_e_falta_de_cobertura():
    """Oleo Comb.: 5.285 mil m3 em 2007 -> 1.083 em 2025, queda de verdade.

    Comparar contra o maximo da serie, em vez de contra a janela vizinha,
    acusaria isto e truncaria 18 anos de historico valido.
    """
    n = len(MESES)
    serie = [440.0 * (0.2 ** (i / n)) ** 1 for i in range(n)]   # -80% no periodo
    r = cobertura.analisar(agg_de({"Óleo Comb.": serie}), MESES)
    assert r["por_produto"]["Óleo Comb."]["inicio"] == MESES[0]


def test_sazonalidade_forte_nao_dispara():
    """Safra e entressafra variam o mes, nunca 10x em janelas de 12 meses."""
    serie = [1000.0 + 400.0 * (i % 12 >= 6) for i in range(len(MESES))]
    r = cobertura.analisar(agg_de({"Diesel B": serie}), MESES)
    assert r["por_produto"]["Diesel B"]["inicio"] == MESES[0]


def test_degrau_no_meio_da_serie_derruba():
    """Produto que some no meio nao e entrada de cobertura: alguem tem de olhar,
    em vez de o painel esconder metade do historico sozinho."""
    meio = len(MESES) // 2
    serie = [1000.0] * meio + [1.0] * 12 + [1000.0] * (len(MESES) - meio - 12)
    with pytest.raises(RuntimeError, match="fora do primeiro quarto"):
        cobertura.analisar(agg_de({"Diesel B": serie}), MESES)


def test_mes_nao_consolidado_fica_fora():
    """O mes corrente tem 0,6% de um mes normal: dentro da janela ele imita
    exatamente a assinatura de falta de cobertura."""
    serie = [1000.0] * (len(MESES) - 1) + [6.0]
    r = cobertura.analisar(agg_de({"Diesel B": serie}), MESES,
                           parciais=[MESES[-1]])
    assert r["por_produto"]["Diesel B"]["inicio"] == MESES[0]


# --- trava de regressao -----------------------------------------------------

def test_janela_que_encurta_derruba():
    with pytest.raises(RuntimeError, match="regressao de cobertura"):
        cobertura.conferir_contra_anterior(
            {"inicio_comparavel": "2010-03"},
            {"cobertura": {"inicio_comparavel": "2007-01"}})


def test_janela_que_alarga_passa():
    cobertura.conferir_contra_anterior(
        {"inicio_comparavel": "2007-01"},
        {"cobertura": {"inicio_comparavel": "2010-03"}})


def test_sem_artefato_anterior_passa():
    cobertura.conferir_contra_anterior({"inicio_comparavel": "2010-03"}, None)


def test_artefato_anterior_sem_cobertura_passa():
    """Rodada anterior gerada antes deste modulo existir."""
    cobertura.conferir_contra_anterior({"inicio_comparavel": "2010-03"},
                                       {"months": ["2007-01"]})
