# guia-tv

Dos herramientas para ver la programación de la TV española **varios días atrás**,
que es justo lo que no deja hacer la web de tvguia.es.

## Lo que descubrí

- **tvguia.es**: los botones solo ofrecen *anteayer, ayer, hoy y mañana*, pero el
  endpoint que pinta la parrilla
  (`/program/ajax/<tpl>/<sets>/<mes>/<día>/<hora>/<min>/<colores>`) **no filtra la
  fecha**. Sirve datos de ~10 días atrás y del día siguiente. El límite es solo de
  la interfaz.
- **Movistar+** tiene una API JSON pública, sin autenticación ni clave, con 149
  canales: ~9 días atrás y ~12 adelante. Es lo más cómodo para consultar o para
  montar una web encima.

## 1. Más días en tvguia.es (bookmarklet)

`tvguia-mas-dias.user.js` sustituye la fila de días original por una única fila
ordenada de 14 botones (10 días atrás y 3 adelante), deja la fila de horas en su
propia línea y atenúa los días de los que no hay datos a la hora seleccionada.

### Instalación

Abre **<https://proyectos-cantelar.github.io/guia-tv/>** y arrastra el botón a la
barra de marcadores. **Sustituye con él tu marcador de tvguia.es**: es un 2x1.

- Si ya estás en tvguia.es, lo pulsas y aparece la parrilla ampliada.
- Si estás en otra página, te lleva a la parrilla de tvguia.es; púlsalo otra vez.

Ese segundo clic es inevitable: un marcador no puede ejecutar código en la página
siguiente (seguridad del navegador). Aun así son los mismos clics que antes y un
marcador menos. Para cero clics, usa el userscript de más abajo.

El marcador no lleva el código dentro, sino que inyecta `tvguia-mas-dias.js` desde
GitHub Pages con `?t=Date.now()` para saltarse la caché. Por eso **siempre ejecuta
la última versión publicada** y no hay que reinstalarlo cuando cambiemos el script.

### Compilar en local

```bash
./generar-bookmarklet.py                      # usa el remote de git
./generar-bookmarklet.py --repo owner/repo    # o se lo dices tú
./generar-bookmarklet.py --url https://mi.dominio/   # dominio propio
```

Genera `public/` (está en `.gitignore`, lo produce el CI):

| Fichero | Qué es |
|---|---|
| `index.html` | página de instalación con el enlace que se arrastra |
| `tvguia-mas-dias.js` | el script que descarga el marcador |
| `bookmarklet.txt` | el marcador 2x1 (te lleva a la parrilla y la amplía) |
| `bookmarklet-inline.txt` | igual pero con el código dentro, congelado en esta versión |

### Despliegue

`.github/workflows/pages.yml` compila en cada push a `main`, valida el JS con
`node --check` y publica `public/` con `actions/deploy-pages`. Hay que activarlo
una vez en **Settings → Pages → Source: GitHub Actions**.

### Otras formas de usarlo

- **Userscript:** instala [Tampermonkey](https://www.tampermonkey.net/) (o
  Violentmonkey) y arrastra el `.user.js` a una pestaña nueva. Se aplica solo.
- **Consola:** pega el contenido del `.user.js` en DevTools para probar cambios.

## 2. CLI `guia-tv.py`

Solo biblioteca estándar de Python (3.9+).

```bash
./guia-tv.py canales                      # los 149 canales con su dial
./guia-tv.py parrilla                     # hoy, generalistas
./guia-tv.py parrilla ayer -c "la 1" -c antena3
./guia-tv.py parrilla -4 -c telecinco     # hace 4 días
./guia-tv.py parrilla 24/10 --json        # JSON, para una web

./guia-tv.py buscar "la revuelta" --dias 8
./guia-tv.py buscar "eurovisión" --dias 8 --todos   # los 149 canales
```

Fechas aceptadas: `hoy`, `ayer`, `anteayer`, `mañana`, `-4`, `2026-10-24`, `24/10`.

### API que usa

```
GET https://ottcache.dof6.com/movistarplus/webplayer/OTT/contents/channels
    ?mdrm=true&tlsstream=true&demarcation=18&version=8

GET https://ottcache.dof6.com/movistarplus/webplayer/OTT/epg
    ?from=YYYY-MM-DDT00:00:00&span=1&channel=<CodCadenaTv>
    &version=8&mdrm=true&tlsstream=true&demarcation=18
```

`from` va en hora local de Madrid y `span` está en días. Los programas traen
`Titulo`, `Temporada`, `TituloEpisodio`, `GeneroComAntena`, `Duracion` y las horas
en epoch en milisegundos. Conviene mandar cabecera `Referer:
https://www.movistarplus.es/programacion-tv`.

## Alternativas que miré

| Fuente | Días atrás | Formato |
|---|---|---|
| tvguia.es (ajax) | ~10 | HTML |
| Movistar+ OTT | ~9 | JSON |
| [epgshare01](https://epgshare01.online/) (`epg_ripper_ES1.xml.gz`) | ~2 | XMLTV |
| [iptv-org/epg](https://github.com/iptv-org/epg) | configurable | XMLTV |
| mi.tv | — | no cubre España |

Data de los datos: no hay soporte oficial; si algún día cambian las rutas, revisa
`window.tvmachine` en la consola de tvguia.es o el grabber `movistarplus.es` de
iptv-org/epg.
