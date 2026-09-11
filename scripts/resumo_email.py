"""Monta o resumo do e-mail mensal a partir do data.js.

Antes isto era um heredoc Python dentro do workflow — uma terceira cópia da
regra de decodificação do data.js, sem teste nenhum cobrindo. Aqui é um script
de verdade, importável e testado.

A manchete usa sempre o **último mês fechado**, nunca o mês da ponta. Em
2026-09-05 o arquivo da ANP trazia agosto com 0,6% do volume normal (três
distribuidoras que anteciparam a declaração) e o e-mail saiu anunciando
"71 mil m³, -99,4% no mês": um alarme falso sobre um mês que não existia ainda.

Escreve pares chave=valor em stdout, no formato do $GITHUB_OUTPUT.
"""
import sys
from collections import defaultdict
from pathlib import Path

import data_js

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data.js"


def _br(valor: float, casas: int = 0) -> str:
    """Formata número no padrão brasileiro (1.234,5)."""
    txt = f"{valor:,.{casas}f}"
    return txt.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def resumo(d: dict) -> dict:
    meses = d["months"]
    parciais = set(data_js.parciais(d))
    completos = [i for i, m in enumerate(meses) if m not in parciais]
    if not completos:
        raise RuntimeError("nenhum mês fechado no data.js — nada a reportar")

    ult = completos[-1]
    ant = completos[-2] if len(completos) > 1 else None
    # Mesmo mês do ano anterior: numa série com sazonalidade forte (safra,
    # entressafra, dias úteis), a variação contra o mês anterior diz pouco.
    # O YoY é a leitura que um analista usa.
    alvo_yoy = f"{int(meses[ult][:4]) - 1}-{meses[ult][5:7]}"
    i_yoy = meses.index(alvo_yoy) if alvo_yoy in meses else None

    por_mes = [0.0] * len(meses)
    por_comp = defaultdict(float)
    por_prod = defaultdict(float)
    for m, c, _, _, p, q in data_js.iter_linhas(d):
        por_mes[m] += q
        if m == ult:
            por_comp[c] += q
            if p is not None:
                por_prod[p] += q

    vol = por_mes[ult]
    var_mes = (vol / por_mes[ant] - 1) * 100 if ant is not None and por_mes[ant] else None
    var_yoy = (vol / por_mes[i_yoy] - 1) * 100 if i_yoy is not None and por_mes[i_yoy] else None

    top = max(por_comp, key=por_comp.get) if por_comp else None
    share = por_comp[top] / vol * 100 if top is not None and vol else 0.0

    # HHI sobre o share de cada companhia no mês — leitura de concentração do
    # mercado de distribuição, que é o que interessa a este público.
    hhi = sum((v / vol * 100) ** 2 for v in por_comp.values()) if vol else 0.0

    mix = " · ".join(
        f"{d['prods'][p]} {v / vol * 100:.1f}%"
        for p, v in sorted(por_prod.items(), key=lambda x: -x[1])
    ) if vol else ""

    # Penetração do etanol hidratado no ciclo Otto (etanol / etanol + gasolina C),
    # em volume. É o indicador que sinaliza a substituição na bomba.
    otto = {d["prods"][p]: v for p, v in por_prod.items()}
    e, g = otto.get("Etanol Hidratado", 0.0), otto.get("Gasolina C", 0.0)
    penetracao = e / (e + g) * 100 if (e + g) else None

    aviso = ""
    if parciais:
        aviso = (
            "<p style='background:#fff8e1;border-left:3px solid #d29922;padding:8px 12px;margin:12px 0'>"
            f"<b>{', '.join(sorted(parciais))}</b> já aparece no arquivo da ANP mas ainda não está "
            "consolidado (poucos agentes declararam). Está marcado no dashboard e fora de todas as "
            "médias, acumulados e comparações — inclusive deste e-mail.</p>"
        )

    return {
        "mes": meses[ult],
        "vol": _br(vol),
        "var": f"{var_mes:+.1f}" if var_mes is not None else "n/d",
        "var_yoy": f"{var_yoy:+.1f}" if var_yoy is not None else "n/d",
        "mes_yoy": alvo_yoy if i_yoy is not None else "n/d",
        "top_comp": d["comps"][top] if top is not None else "n/d",
        "top_share": f"{share:.1f}",
        "hhi": _br(hhi),
        "periodo": f"{meses[0]} a {meses[ult]}",
        "mix_li": f"<li>Mix do mês: <b>{mix}</b></li>" if mix else "",
        "otto_li": (f"<li>Etanol hidratado no ciclo Otto: <b>{penetracao:.1f}%</b> do volume "
                    "(etanol ÷ etanol + gasolina C)</li>") if penetracao is not None else "",
        "aviso_parcial": aviso,
    }


def main():
    d = data_js.carregar(OUT)
    if d is None:
        print("data.js ilegível", file=sys.stderr)
        raise SystemExit(1)
    for chave, valor in resumo(d).items():
        # Valores multilinha quebrariam o formato chave=valor do $GITHUB_OUTPUT.
        print(f"{chave}={str(valor).replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
