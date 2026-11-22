"""Rotulo do arquivo da ANP contra o conteudo, e o que vai para o artefato.

`Liquidos_Vendas_Historico_2007_a_2017.csv` cobre 2007-01 a 2016-12. O ano de
2017 inteiro nao esta nele, apesar do nome -- e e por isso que 2017 precisa ser
herdado do artefato anterior, ou seja, deixou de ser reproduzivel a partir do
zip de hoje. Se a cadeia de artefatos se romper, esses 12 meses se perdem, e
isso tem de estar ESCRITO no artefato, nao descoberto por acidente.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import membros as mod_membros  # noqa: E402
import update_dashboard as ud  # noqa: E402

# --- o nome do arquivo ------------------------------------------------------

def test_faixa_declarada_le_o_nome():
    assert mod_membros.faixa_declarada(
        "Liquidos_Vendas_Historico_2007_a_2017.csv") == ("2007-01", "2017-12")


def test_membro_sem_faixa_no_nome_nao_promete_nada():
    assert mod_membros.faixa_declarada("Liquidos_Vendas_Atual.csv") is None


def test_divergencia_de_rotulo_e_o_caso_real_de_2017():
    d = mod_membros.divergencias_de_rotulo({
        "Liquidos_Vendas_Historico_2007_a_2017.csv":
            mod_membros.meses_entre("2007-01", "2016-12"),
    })
    assert len(d) == 1
    assert d[0]["declarado"] == ["2007-01", "2017-12"]
    assert d[0]["real"] == ["2007-01", "2016-12"]
    assert len(d[0]["faltando"]) == 12
    assert d[0]["faltando"][0] == "2017-01"


def test_rotulo_que_bate_nao_e_divergencia():
    assert mod_membros.divergencias_de_rotulo({
        "Liquidos_Vendas_Historico_2018_a_2023.csv":
            mod_membros.meses_entre("2018-01", "2023-12"),
    }) == []


def test_membro_sem_faixa_nunca_e_divergencia():
    assert mod_membros.divergencias_de_rotulo({
        "Liquidos_Vendas_Atual.csv": mod_membros.meses_entre("2024-01", "2026-09"),
    }) == []


# --- o que o artefato passa a carregar --------------------------------------

MESES = [f"{a}-{m:02d}" for a in range(2007, 2027) for m in range(1, 13)][:237]


def cubo(series: dict, uf="SP") -> dict:
    return {(mes, "DISTRIB", uf, "TRR", prod): v
            for prod, serie in series.items()
            for mes, v in zip(MESES, serie, strict=True) if v}


def test_artefato_grava_a_janela_comparavel():
    """O degrau do diesel tem de chegar ao painel, nao ficar no log."""
    agg = cubo({
        "Diesel B": [1.0] * 36 + [3000.0] * (len(MESES) - 36),
        "Gasolina C": [1600.0] * len(MESES),
    })
    d = ud.gerar_data_js(agg, fonte={})
    assert d["cobertura"]["inicio_comparavel"] == MESES[37]
    assert d["cobertura"]["por_produto"]["Gasolina C"]["inicio"] == MESES[0]


def test_artefato_marca_a_uf_nao_geografica():
    """"NI" e o destino que o declarante nao informou, nao um estado.

    Fica nos dados e no total -- descartar 0,5% do volume para limpar o mapa
    seria trocar um erro de geografia por um erro de volume. Sai so do ranking
    geografico, e o painel le isto daqui em vez de ter a regra duplicada.
    """
    agg = cubo({"Gasolina C": [1600.0] * len(MESES)}, uf="SP")
    agg.update(cubo({"Gasolina C": [8.0] * len(MESES)}, uf="NI"))
    d = ud.gerar_data_js(agg, fonte={})
    assert d["ufs_nao_geograficas"] == ["NI"]
    assert "NI" in d["ufs"]          # continua no cubo
    assert "SP" in d["ufs"]


def test_sem_uf_nao_geografica_a_lista_fica_vazia():
    agg = cubo({"Gasolina C": [1600.0] * len(MESES)})
    assert ud.gerar_data_js(agg, fonte={})["ufs_nao_geograficas"] == []
