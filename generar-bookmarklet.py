#!/usr/bin/env python3
"""Compila el bookmarklet y los ficheros que se publican en GitHub Pages.

Toma `tvguia-mas-dias.user.js` como única fuente de verdad y escribe en `public/`:

  tvguia-mas-dias.js       el script servido (sin la cabecera de userscript)
  bookmarklet.txt          el marcador "cargador": descarga siempre la última versión
  bookmarklet-inline.txt   el marcador autocontenido (no se actualiza solo)
  index.html               página de instalación con el enlace que se arrastra

Uso:
    python3 generar-bookmarklet.py                      # detecta el repo del remote git
    python3 generar-bookmarklet.py --repo owner/repo    # o se lo dices tú
    python3 generar-bookmarklet.py --url https://mi.dominio/   # dominio propio

En GitHub Actions el repo llega por $GITHUB_REPOSITORY.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FUENTE = AQUI / "tvguia-mas-dias.user.js"
SALIDA = AQUI / "public"

NOMBRE = "TVguia +días"
NOMBRE_SCRIPT = "tvguia-mas-dias.js"
REPO_POR_DEFECTO = "Proyectos-Cantelar/guia-tv"


# --------------------------------------------------------------------------- #
# Compilación
# --------------------------------------------------------------------------- #
def sin_cabecera(codigo: str) -> str:
    """Quita el bloque // ==UserScript== ... // ==/UserScript==."""
    return re.sub(r"// ==UserScript==.*?// ==/UserScript==\s*", "", codigo, flags=re.S)


def minifica(codigo: str) -> str:
    """Minificado conservador: fuera comentarios, sangría y líneas vacías."""
    codigo = sin_cabecera(codigo)
    codigo = re.sub(r"/\*.*?\*/", "", codigo, flags=re.S)

    lineas = []
    for linea in codigo.splitlines():
        s = linea.strip()
        if not s or s.startswith("//"):
            continue
        # comentario al final de línea: solo si la línea no lleva cadenas
        if not any(c in s for c in "\"'`"):
            s = re.sub(r"\s+//.*$", "", s)
        lineas.append(s)
    return "\n".join(lineas)


def a_bookmarklet(codigo: str) -> str:
    return "javascript:" + urllib.parse.quote(codigo, safe="")


def repo_desde_git() -> str | None:
    try:
        salida = subprocess.run(
            ["git", "-C", str(AQUI), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except Exception:
        return None
    return repo_desde_url(salida)


def repo_desde_url(url: str) -> str | None:
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    return f"{m[1]}/{m[2]}" if m else None


def url_de_pages(repo: str) -> str:
    owner, nombre = repo.split("/", 1)
    host = f"{owner.lower()}.github.io"
    if nombre.lower() == host:
        return f"https://{host}/"
    return f"https://{host}/{nombre}/"


# --------------------------------------------------------------------------- #
# Piezas publicadas
# --------------------------------------------------------------------------- #
def codigo_cargador(url_script: str) -> str:
    """Marcador diminuto que inyecta el script desde GitHub Pages.

    Se le añade un parámetro con la hora para saltarse la caché de Pages (~10 min),
    así el marcador instalado no hay que tocarlo nunca más.
    """
    return (
        "(function(){"
        "var s=document.createElement('script');"
        f"s.src={url_script!r}+'?t='+Date.now();"
        "s.onerror=function(){console.error('[guia-tv] no se pudo cargar el script');};"
        "(document.body||document.documentElement).appendChild(s);"
        "})();"
    )


PLANTILLA = """<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITULO@@</title>
<style>
  body{font:16px/1.6 system-ui,sans-serif;margin:0 auto;padding:2rem 1.25rem;max-width:46rem;color:#111}
  h1{font-size:1.6rem;margin:0 0 .25rem}
  h2{font-size:1.15rem;margin:2rem 0 .5rem}
  p.sub{color:#555;margin:0 0 2rem}
  a.btn{display:inline-block;padding:.6rem 1.1rem;background:#a3d7ff;color:#000;
        font-weight:700;text-decoration:none;border-radius:4px;border:1px solid #7cc3f5}
  a.btn:hover{background:#8ecdf9}
  a.btn.alt{background:#e6e6e6;border-color:#c9c9c9}
  code{background:#f1f1f1;padding:.1rem .3rem;border-radius:3px}
  textarea{width:100%;height:7rem;margin-top:.75rem;font:12px/1.4 monospace}
  ul{padding-left:1.2rem}
  footer{margin-top:3rem;color:#777;font-size:.85rem}
  details{margin:.5rem 0}
  summary{cursor:pointer;font-weight:600}
</style>
<h1>@@TITULO@@</h1>
<p class="sub">Más días en la parrilla de tvguia.es.</p>

<p>Arrastra este enlace a la barra de marcadores:</p>
<p><a class="btn" href="@@CARGADOR@@">@@NOMBRE@@</a></p>
<p>Luego entra en <a href="https://www.tvguia.es/programacion-tv/programacion-tv">tvguia.es</a>
y pulsa el marcador. El marcador descarga
<a href="@@SCRIPT@@">@@SCRIPT@@</a> de esta misma página con un parámetro
antiguo de caché, así que <strong>siempre ejecuta la última versión</strong>: si el
script cambia, no tienes que volver a instalarlo.</p>

<h2>Qué hace</h2>
<ul>
  <li>Sustituye la fila de días original (que solo llega a 2 días atrás) por una
      fila ordenada de 14 botones: 10 días atrás y 3 adelante.</li>
  <li>Deja la fila de horas en su propia línea.</li>
  <li>Atenúa los días de los que no hay datos a la hora seleccionada.</li>
</ul>

<h2>Otras formas de instalarlo</h2>
<details>
  <summary>Marcador autocontenido (no se actualiza solo)</summary>
  <p>Lleva el código dentro, así que funciona aunque esta página no responda o
     bloquees scripts de terceros. A cambio, se queda congelado en la versión actual.</p>
  <p><a class="btn alt" href="@@INLINE@@">@@NOMBRE@@ (fijo)</a></p>
</details>
<details>
  <summary>Copiar la URL a mano</summary>
  <p>Crea un marcador y pega dentro esto:</p>
  <textarea readonly>@@CARGADOR_TXT@@</textarea>
</details>

<footer>Generado el @@FECHA@@ desde <code>@@FUENTE@@</code>.</footer>
</html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                   help=f"owner/repo del proyecto en GitHub (por defecto: {REPO_POR_DEFECTO})")
    p.add_argument("--url", help="URL base de Pages, si usas dominio propio")
    args = p.parse_args()

    repo = args.repo or repo_desde_git() or REPO_POR_DEFECTO
    base = args.url or url_de_pages(repo)
    if not base.endswith("/"):
        base += "/"

    codigo = minifica(FUENTE.read_text(encoding="utf-8"))
    url_script = base + NOMBRE_SCRIPT
    cargador = a_bookmarklet(codigo_cargador(url_script))
    inline = a_bookmarklet(codigo)

    SALIDA.mkdir(exist_ok=True)
    (SALIDA / NOMBRE_SCRIPT).write_text(sin_cabecera(FUENTE.read_text(encoding="utf-8")), encoding="utf-8")
    (SALIDA / "bookmarklet.txt").write_text(cargador + "\n", encoding="utf-8")
    (SALIDA / "bookmarklet-inline.txt").write_text(inline + "\n", encoding="utf-8")

    pagina = PLANTILLA
    for token, valor in {
        "@@TITULO@@": "guia-tv — más días en tvguia.es",
        "@@NOMBRE@@": NOMBRE,
        "@@SCRIPT@@": NOMBRE_SCRIPT,
        "@@FUENTE@@": FUENTE.name,
        "@@FECHA@@": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "@@CARGADOR_TXT@@": html.escape(cargador),
        "@@CARGADOR@@": html.escape(cargador, quote=True),
        "@@INLINE@@": html.escape(inline, quote=True),
    }.items():
        pagina = pagina.replace(token, valor)
    (SALIDA / "index.html").write_text(pagina, encoding="utf-8")

    print(f"repo        : {repo}")
    print(f"pages       : {base}")
    print(f"código      : {len(codigo)} caracteres")
    print(f"cargador    : {len(cargador)} caracteres")
    print(f"inline      : {len(inline)} caracteres")
    print(f"salida      : {SALIDA}/ (index.html, {NOMBRE_SCRIPT}, bookmarklet.txt, bookmarklet-inline.txt)")


if __name__ == "__main__":
    main()
