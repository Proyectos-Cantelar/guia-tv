#!/usr/bin/env python3
"""guia-tv.py — parrilla de la televisión española desde la API pública de Movistar+.

La guía de Movistar+ (ottcache.dof6.com) es un JSON sin autenticación que sirve
unos ~9 días atrás y ~12 adelante, con 149 canales. Es la fuente más cómoda para
consultar "qué echaron tal día" sin depender de una web con navegación limitada.

Uso:
    ./guia-tv.py canales
    ./guia-tv.py parrilla                # hoy, canales generalistas
    ./guia-tv.py parrilla ayer -c "la 1" -c "antena 3"
    ./guia-tv.py parrilla 2026-10-24 -c telecinco
    ./guia-tv.py buscar "la revuelta" --dias 8
    ./guia-tv.py buscar "eurovisión" --dias 8 --todos
    ./guia-tv.py parrilla -4 --json      # salida JSON (para una web)

Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://ottcache.dof6.com/movistarplus/webplayer/OTT"
QUERY = "version=8&mdrm=true&tlsstream=true&demarcation=18"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://www.movistarplus.es/programacion-tv",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
}
MADRID = ZoneInfo("Europe/Madrid")

# Canales que se muestran si no se pide ninguno.
GENERALISTAS = ["la 1", "la 2", "antena 3", "cuatro", "telecinco", "la sexta"]

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def canales() -> list[dict]:
    return _get(f"{BASE}/contents/channels?{QUERY}")


def epg(channel_id: str, dia: date) -> list[dict]:
    """Programas de un canal para un día (hora local de Madrid)."""
    desde = f"{dia.isoformat()}T00:00:00"
    url = f"{BASE}/epg?from={urllib.parse.quote(desde)}&span=1&channel={urllib.parse.quote(channel_id)}&{QUERY}"
    try:
        datos = _get(url)
    except Exception as exc:  # 404 / vacío / red
        print(f"  ! {channel_id} {dia}: {exc}", file=sys.stderr)
        return []
    return datos if isinstance(datos, list) else []


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def normaliza(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def busca_canal(nombre: str, todos: list[dict]) -> dict:
    def clave(t: str) -> str:
        return normaliza(t).replace(" ", "")

    objetivo = clave(nombre)
    exactos = [c for c in todos if clave(c.get("Nombre", "")) == objetivo]
    if exactos:
        return exactos[0]
    parciales = [c for c in todos if objetivo in clave(c.get("Nombre", ""))]
    if len(parciales) == 1:
        return parciales[0]
    if parciales:
        opciones = ", ".join(c["Nombre"] for c in parciales[:10])
        raise SystemExit(f"Canal ambiguo: {nombre!r}. Coinciden: {opciones}")
    raise SystemExit(f"No encuentro el canal {nombre!r}. Prueba con: ./guia-tv.py canales")


def parsea_fecha(valor: str) -> date:
    hoy = datetime.now(MADRID).date()
    v = valor.strip().lower()
    relativos = {
        "hoy": 0, "ayer": -1, "anteayer": -2, "antier": -2,
        "mañana": 1, "manana": 1, "pasado mañana": 2,
    }
    if v in relativos:
        return hoy + timedelta(days=relativos[v])
    if re.fullmatch(r"[+-]?\d{1,2}", v):
        return hoy + timedelta(days=int(v))
    dia, mes, anio = None, None, None
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v):
        anio, mes, dia = int(m[1]), int(m[2]), int(m[3])
    elif m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", v):
        dia, mes = int(m[1]), int(m[2])
        anio = int(m[3]) if m[3] else hoy.year
        if anio < 100:
            anio += 2000
    if not (dia and mes and anio):
        raise SystemExit(f"Fecha no válida: {valor!r} (usa hoy/ayer/-3/2026-10-24/24-10)")
    return date(anio, mes, dia)


def inicio(p: dict) -> datetime:
    return datetime.fromtimestamp(int(p["FechaHoraInicio"]) / 1000, MADRID)


def fin(p: dict) -> datetime:
    return datetime.fromtimestamp(int(p["FechaHoraFin"]) / 1000, MADRID)


def titulo(p: dict) -> str:
    return (p.get("Titulo") or "").strip()


def a_registro(canal: dict, p: dict) -> dict:
    t = titulo(p)
    temp = (p.get("Temporada") or "").strip("() ")
    ep = (p.get("TituloEpisodio") or "").replace('"', "").strip()
    extra = []
    if temp:
        extra.append(temp)
    if ep and normaliza(ep) != normaliza(t):
        extra.append(ep)
    return {
        "canal": canal.get("Nombre"),
        "dial": canal.get("Dial"),
        "inicio": inicio(p).isoformat(timespec="minutes"),
        "fin": fin(p).isoformat(timespec="minutes"),
        "titulo": t,
        "temporada_episodio": " ".join(extra) or None,
        "genero": p.get("GeneroComAntena") or None,
        "duracion_min": p.get("Duracion"),
    }


def programas_del_dia(canal: dict, dia: date) -> list[dict]:
    """Programas que se emiten ese día local (recorta los de la madrugada vecina)."""
    items = []
    for p in epg(canal["CodCadenaTv"], dia):
        if not p.get("FechaHoraInicio"):
            continue
        if fin(p) <= datetime.combine(dia, datetime.min.time(), MADRID):
            continue
        if inicio(p) >= datetime.combine(dia + timedelta(days=1), datetime.min.time(), MADRID):
            continue
        items.append(p)
    items.sort(key=inicio)
    return items


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #
def cmd_canales(args) -> None:
    todos = canales()
    if args.json:
        print(json.dumps(todos, ensure_ascii=False, indent=2))
        return
    for c in sorted(todos, key=lambda c: (c.get("Dial") or 999, c.get("Nombre") or "")):
        print(f"{c.get('Dial'):>4}  {c.get('Nombre'):<32} {c['CodCadenaTv']}")


def cmd_parrilla(args) -> None:
    dia = parsea_fecha(args.fecha)
    todos = canales()
    elegidos = [busca_canal(n, todos) for n in (args.canal or GENERALISTAS)]

    salida = []
    for canal in elegidos:
        for p in programas_del_dia(canal, dia):
            salida.append(a_registro(canal, p))

    if args.json:
        print(json.dumps(salida, ensure_ascii=False, indent=2))
        return

    print(f"{DIAS_ES[dia.weekday()]} {dia.strftime('%d/%m/%Y')} — {len(salida)} programas\n")
    actual = None
    for r in salida:
        if r["canal"] != actual:
            actual = r["canal"]
            print(f"\n== {actual} ==")
        cuando = datetime.fromisoformat(r["inicio"])
        cola = f"  ({r['temporada_episodio']})" if r["temporada_episodio"] else ""
        if cuando.date() != dia:
            cola += f"  [del {cuando.strftime('%d/%m')}]"
        print(f"  {cuando.strftime('%H:%M')}  {r['titulo']}{cola}")


def cmd_buscar(args) -> None:
    hoy = datetime.now(MADRID).date()
    dias = [hoy - timedelta(days=n) for n in range(0, args.dias)]
    todos = canales()
    if args.todos:
        elegidos = todos
    else:
        elegidos = [busca_canal(n, todos) for n in (args.canal or GENERALISTAS)]

    objetivo = normaliza(args.texto)
    tareas = [(c, d) for d in dias for c in elegidos]

    encontrados = []
    with ThreadPoolExecutor(max_workers=args.paralelo) as pool:
        futuros = {pool.submit(programas_del_dia, c, d): (c, d) for c, d in tareas}
        for fut in futuros:
            canal, _ = futuros[fut]
            try:
                for p in fut.result():
                    if objetivo in normaliza(titulo(p)):
                        encontrados.append(a_registro(canal, p))
            except Exception as exc:
                print(f"  ! {canal.get('Nombre')}: {exc}", file=sys.stderr)

    encontrados.sort(key=lambda r: r["inicio"], reverse=True)
    # Un programa que cruza la medianoche sale en dos días seguidos: nos quedamos con uno.
    vistos = set()
    unicos = []
    for r in encontrados:
        clave = (r["canal"], r["inicio"], r["titulo"])
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(r)
    encontrados = unicos

    if args.json:
        print(json.dumps(encontrados, ensure_ascii=False, indent=2))
        return

    if not encontrados:
        print(f"Sin resultados para {args.texto!r} en los últimos {args.dias} días "
              f"({len(elegidos)} {'canal' if len(elegidos) == 1 else 'canales'}).")
        return

    plural = "canal" if len(elegidos) == 1 else "canales"
    print(f"{len(encontrados)} emisiones de {args.texto!r} "
          f"(últimos {args.dias} días, {len(elegidos)} {plural})\n")
    for r in encontrados:
        cuando = datetime.fromisoformat(r["inicio"])
        dia_txt = cuando.strftime("%d/%m")
        print(f"  {dia_txt} {cuando.strftime('%H:%M')}  {r['canal']:<18} {r['titulo']}")


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(
        description="Parrilla de TV española (API de Movistar+, ~9 días atrás / ~12 adelante).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("canales", help="lista los canales disponibles")
    pc.add_argument("--json", action="store_true")
    pc.set_defaults(func=cmd_canales)

    pp = sub.add_parser("parrilla", help="parrilla de un día")
    pp.add_argument("fecha", nargs="?", default="hoy",
                    help="hoy (por defecto), ayer, -3, 2026-10-24, 24-10")
    pp.add_argument("-c", "--canal", action="append", help="canal (repetible)")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_parrilla)

    pb = sub.add_parser("buscar", help="busca un título en los últimos días")
    pb.add_argument("texto")
    pb.add_argument("--dias", type=int, default=7, help="días hacia atrás (por defecto 7)")
    pb.add_argument("-c", "--canal", action="append", help="canal (repetible)")
    pb.add_argument("--todos", action="store_true", help="busca en los 149 canales")
    pb.add_argument("--paralelo", type=int, default=8, help="peticiones simultáneas")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(func=cmd_buscar)

    args = p.parse_args()
    if getattr(args, "dias", 0) and args.dias > 15:
        raise SystemExit("La API solo guarda ~9 días atrás; usa --dias 9 como máximo.")
    args.func(args)


if __name__ == "__main__":
    main()
