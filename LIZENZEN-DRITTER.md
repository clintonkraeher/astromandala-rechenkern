# Lizenzen der Bestandteile

Stand 20.11.2026, zu den Versionen in `requirements.txt`. Die Angaben stammen aus den Metadaten
der Pakete; massgeblich sind die Lizenztexte, die jedes Paket selbst mitbringt (im Image unter
`site-packages/<paket>.dist-info/`).

| Bestandteil | Version | Lizenz | Quelle |
|---|---|---|---|
| libephemeris | 3.2.2 | AGPL-3.0-only | https://github.com/g-battaglia/libephemeris |
| gunicorn | 26.2.0 | MIT | https://gunicorn.org |
| numpy | 2.5.5 | BSD-3-Clause und weitere freizuegige (0BSD, MIT, Zlib, CC0-1.0) | https://numpy.org |
| skyfield | 1.55 | MIT | https://github.com/skyfielders/python-skyfield |
| skyfield-data | 7.0.0 | MIT | https://github.com/brunobord/skyfield-data |
| jplephem | 2.24 | MIT | https://github.com/brandon-rhodes/python-jplephem |
| sgp4 | 2.27 | MIT | https://github.com/brandon-rhodes/python-sgp4 |
| pyerfa | 2.0.1.5 | BSD-3-Clause | https://github.com/liberfa/pyerfa |
| click | 8.5.1 | BSD-3-Clause | https://github.com/pallets/click |
| zstandard | 0.25.0 | BSD-3-Clause | https://github.com/indygreg/python-zstandard |
| certifi | 2026.10.23 | MPL-2.0 | https://github.com/certifi/python-certifi |
| Python | 3.13 | PSF-2.0 | https://www.python.org |

Das Extra `nbody` von libephemeris wird nicht installiert.

## Daten

- `base_core.leb2` und `base_asteroids.leb2`: Koeffizienten aus dem Release `data-v4` von
  libephemeris, abgeleitet aus den Ephemeriden DE440/DE441 und den Kleinkoerperbahnen des NASA
  Jet Propulsion Laboratory. Die Dateien liegen unveraendert im Image.
- `tests/referenz.json`: Vergleichswerte aus JPL Horizons (https://ssd.jpl.nasa.gov/horizons/),
  abgerufen am 20.11.2026.

libephemeris nennt die Herkunft seiner eigenen Bestandteile in `NOTICE.md` und
`THIRD_PARTY_NOTICES.md` (im Image unter `site-packages/libephemeris-3.2.2.dist-info/licenses/`).
