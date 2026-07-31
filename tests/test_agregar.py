"""Testes da agregacao do CSV da ANP.

O CSV e lido por indice de coluna (a ANP nao documenta um cabecalho estavel).
O risco disso e uma mudanca de layout produzir numeros errados em silencio --
estes testes travam o comportamento de falhar alto em vez de gravar lixo.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import update_dashboard as ud  # noqa: E402

CAB = ";".join(f"c{i}" for i in range(15))


def csv_bytes(*linhas):
    return ("\n".join([CAB, *linhas]) + "\n").encode("latin-1")


def linha(ano=2026, mes=5, comp="DISTRIB A", uf="SP", mkt="TRR", qtd="1.234,50"):
    campos = [""] * 15
    campos[ud.COL_ANO], campos[ud.COL_MES] = str(ano), str(mes)
    campos[ud.COL_COMP], campos[ud.COL_UF] = comp, uf
    campos[ud.COL_MKT], campos[ud.COL_QTD] = mkt, qtd
    return ";".join(campos)


def test_soma_por_chave():
    agg = ud.agregar(csv_bytes(linha(qtd="10,5"), linha(qtd="4,5")))
    assert agg[("2026-05", "DISTRIB A", "SP", "TRR")] == pytest.approx(15.0)


def test_mes_recebe_zero_a_esquerda():
    agg = ud.agregar(csv_bytes(linha(mes=3, qtd="1,0")))
    assert ("2026-03", "DISTRIB A", "SP", "TRR") in agg


def test_cabecalho_curto_derruba():
    """Coluna a menos = layout mudou; melhor falhar do que somar a coluna errada."""
    curto = ("c0;c1;c2\n" + "2026;5;X\n").encode("latin-1")
    with pytest.raises(RuntimeError, match="colunas"):
        ud.agregar(curto)


def test_csv_vazio_derruba():
    with pytest.raises(RuntimeError):
        ud.agregar(b"")


def test_sem_linhas_de_dados_derruba():
    with pytest.raises(RuntimeError, match="linhas de dados"):
        ud.agregar((CAB + "\n").encode("latin-1"))


def test_muitas_linhas_invalidas_derrubam():
    """Se a coluna de mes virar texto, a rotina para em vez de gravar lixo."""
    ruins = [linha(mes=99) for _ in range(50)]
    with pytest.raises(RuntimeError, match="layout"):
        ud.agregar(csv_bytes(*ruins))


def test_poucas_linhas_invalidas_sao_toleradas():
    boas = [linha(qtd="1,0") for _ in range(300)]
    agg = ud.agregar(csv_bytes(*boas, linha(mes=13)))
    assert agg[("2026-05", "DISTRIB A", "SP", "TRR")] == pytest.approx(300.0)


def test_regressao_de_meses_derruba():
    anterior = {"months": ["2026-04", "2026-05"], "rows": [0] * 10}
    novo = {"months": ["2026-04"], "rows": [0] * 10}
    with pytest.raises(RuntimeError, match="regressao"):
        ud.conferir_contra_anterior(novo, anterior)


def test_regressao_de_combinacoes_derruba():
    anterior = {"months": ["2026-05"], "rows": [0] * (5 * 1000)}
    novo = {"months": ["2026-05"], "rows": [0] * (5 * 800)}
    with pytest.raises(RuntimeError, match="regressao"):
        ud.conferir_contra_anterior(novo, anterior)


def test_crescimento_normal_passa():
    anterior = {"months": ["2026-04"], "rows": [0] * (5 * 1000)}
    novo = {"months": ["2026-04", "2026-05"], "rows": [0] * (5 * 1100)}
    ud.conferir_contra_anterior(novo, anterior)  # nao levanta


def test_sem_anterior_nao_bloqueia():
    ud.conferir_contra_anterior({"months": ["2026-05"], "rows": []}, None)
