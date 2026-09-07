"""Testes do resumo do e-mail.

O e-mail de 2026-09-05 saiu com a manchete "2026-08: 71 mil m³ (-99,4% no mês)"
porque o resumo lia sempre o último mês do arquivo. Estes testes travam a regra
nova: a manchete é do último mês FECHADO, e o mês em formação vira aviso.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import data_js  # noqa: E402
import resumo_email as re_  # noqa: E402
import update_dashboard as ud  # noqa: E402


def arquivo(months, por_mes, parciais=None, prods=("Diesel B", "Gasolina C", "Etanol Hidratado")):
    """data.js sintético: `por_mes` é {indice_mes: [(comp, prod, volume), ...]}."""
    comps = sorted({c for linhas in por_mes.values() for c, _, _ in linhas})
    rows = []
    for m, linhas in por_mes.items():
        for c, p, v in linhas:
            rows.extend([m, comps.index(c), 0, 0, list(prods).index(p),
                         round(v * data_js.ESCALA)])
    return {"months": list(months), "comps": comps, "ufs": ["SP"], "mkts": ["TRR"],
            "prods": list(prods), "campos": ud.CAMPOS, "rows": rows,
            "parciais": parciais or []}


def test_manchete_usa_o_ultimo_mes_fechado():
    d = arquivo(
        ["2025-07", "2026-06", "2026-07", "2026-08"],
        {0: [("VIBRA", "Diesel B", 1000.0)],
         1: [("VIBRA", "Diesel B", 1000.0)],
         2: [("VIBRA", "Diesel B", 1200.0)],
         3: [("SMALL", "Diesel B", 7.0)]},
        parciais=["2026-08"],
    )
    r = re_.resumo(d)
    assert r["mes"] == "2026-07"
    assert r["vol"] == "1.200"
    assert r["top_comp"] == "VIBRA"          # e não SMALL
    assert "2026-08" in r["aviso_parcial"]


def test_variacao_anual_compara_o_mesmo_mes():
    d = arquivo(
        ["2025-07", "2026-06", "2026-07"],
        {0: [("VIBRA", "Diesel B", 1000.0)],
         1: [("VIBRA", "Diesel B", 500.0)],
         2: [("VIBRA", "Diesel B", 1100.0)]},
    )
    r = re_.resumo(d)
    assert r["mes_yoy"] == "2025-07"
    assert r["var_yoy"] == "+10.0"           # contra jul/25, não contra jun/26
    assert r["var"] == "+120.0"


def test_sem_mes_do_ano_anterior_reporta_nd():
    d = arquivo(["2026-06", "2026-07"],
                {0: [("VIBRA", "Diesel B", 100.0)],
                 1: [("VIBRA", "Diesel B", 110.0)]})
    assert re_.resumo(d)["var_yoy"] == "n/d"


def test_sem_mes_parcial_nao_ha_aviso():
    d = arquivo(["2026-07"], {0: [("VIBRA", "Diesel B", 100.0)]})
    assert re_.resumo(d)["aviso_parcial"] == ""


def test_penetracao_do_etanol_no_ciclo_otto():
    """etanol ÷ (etanol + gasolina C) — o diesel fica de fora da conta."""
    d = arquivo(["2026-07"], {0: [("VIBRA", "Etanol Hidratado", 30.0),
                                  ("VIBRA", "Gasolina C", 70.0),
                                  ("VIBRA", "Diesel B", 900.0)]})
    assert "30.0%" in re_.resumo(d)["otto_li"]


def test_hhi_de_monopolio_e_10000():
    d = arquivo(["2026-07"], {0: [("VIBRA", "Diesel B", 100.0)]})
    assert re_.resumo(d)["hhi"] == "10.000"


def test_hhi_de_quatro_iguais_e_2500():
    d = arquivo(["2026-07"], {0: [(f"C{i}", "Diesel B", 25.0) for i in range(4)]})
    assert re_.resumo(d)["hhi"] == "2.500"


def test_numeros_saem_no_padrao_brasileiro():
    assert re_._br(1234567.0) == "1.234.567"
    assert re_._br(1234.5, 1) == "1.234,5"


def test_arquivo_so_com_mes_parcial_derruba():
    """Sem nenhum mês fechado não há manchete honesta possível: falha alto em
    vez de mandar e-mail com o número do mês em formação."""
    d = arquivo(["2026-08"], {0: [("SMALL", "Diesel B", 7.0)]}, parciais=["2026-08"])
    with pytest.raises(RuntimeError, match="nenhum mês fechado"):
        re_.resumo(d)


def test_saida_e_uma_linha_por_chave():
    """$GITHUB_OUTPUT quebra com valor multilinha."""
    d = arquivo(["2026-07", "2026-08"],
                {0: [("VIBRA", "Diesel B", 100.0)],
                 1: [("SMALL", "Diesel B", 1.0)]}, parciais=["2026-08"])
    for valor in re_.resumo(d).values():
        assert "\n" not in str(valor)
