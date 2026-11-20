# Astromandala Rechenkern

Ein kleiner HTTP-Dienst, der Planetenstaende und Haeuser zu einem Zeitpunkt rechnet. Er ist der
astronomische Rechenkern hinter den Horoskopen von [Astromandala](https://astromandala.at).

Gerechnet wird mit [libephemeris](https://github.com/g-battaglia/libephemeris) auf Grundlage der
Ephemeriden DE440/DE441 des NASA Jet Propulsion Laboratory.

## Was der Kern tut und was nicht

Der Kern bekommt einen Zeitpunkt in UTC, fuer ein Horoskop zusaetzlich Breite und Laenge, und
gibt Zahlen zurueck: ekliptikale Laenge, Breite und Tagesbewegung von vierzehn Koerpern, dazu die
zwoelf Haeuserspitzen, Aszendent und MC.

Er kennt keine Personen, keine Ortsnamen, keine Zeitzonen und keine Deutungstexte. Er speichert
nichts und schreibt keine Eingaben in Protokolle. Im Betrieb hat er kein ausgehendes Netz.

## Lizenz

Copyright (C) 2026 Rhein Ahr Digital

Dieses Programm steht unter der GNU Affero General Public License, Version 3
(`AGPL-3.0-only`). Der Lizenztext liegt in [LICENSE](LICENSE). Es wird ohne jede Gewaehrleistung
bereitgestellt.

libephemeris steht ebenfalls unter `AGPL-3.0-only`. Die Lizenzen aller weiteren Bestandteile
nennt [LIZENZEN-DRITTER.md](LIZENZEN-DRITTER.md).

Jede laufende Fassung nennt unter `GET /quelle` dieses Repository und den Commit, aus dem sie
gebaut wurde.

## Schnittstelle

JSON ueber HTTP. `POST` verlangt `Authorization: Bearer <KERN_TOKEN>` und
`Content-Type: application/json`.

| Pfad | Zweck |
|---|---|
| `GET /health` | Der Kern laeuft und hat seinen Selbsttest bestanden |
| `GET /quelle` | Lizenz, Repository, Commit, Bibliothek und Pruefsummen der Daten |
| `POST /himmel` | Staende zu 1 bis 500 Zeitpunkten, ohne Ort |
| `POST /radix` | Staende, Haeuser, Aszendent und MC zu einem Zeitpunkt und Ort |

Zeitpunkte stehen in UTC nach ISO 8601, zum Beispiel `2026-11-20T12:00:00Z`. Der Kern rechnet
von 1900 bis 2100.

```
POST /himmel
{"zeitpunkte": ["2026-11-20T12:00:00Z", "2026-11-21T12:00:00Z"]}

{"himmel": [{"zeitpunkt": "2026-11-20T12:00:00Z",
             "koerper": [{"name": "Sun", "longitude": 238.2643541, "latitude": 0.0000683,
                          "speed": 1.0111034}, ...]}, ...],
 "rechenstand": {"kern": "1.0.0", "commit": "...", "bibliothek": "libephemeris 3.2.2",
                 "tierkreis": "tropisch"}}
```

```
POST /radix
{"zeitpunkt": "1978-07-14T05:40:00Z", "lat": 47.0707, "lon": 15.4395}

{"zeitpunkt": "1978-07-14T05:40:00Z", "koerper": [...], "haeusersystem": "placidus",
 "haeuser": [137.2696, ...], "aszendent": 137.2696, "mc": 34.4431, "rechenstand": {...}}
```

`koerper` enthaelt immer in dieser Reihenfolge: `Sun`, `Moon`, `Mercury`, `Venus`, `Mars`,
`Jupiter`, `Saturn`, `Uranus`, `Neptune`, `Pluto`, `Chiron`, `Lilith`, `MondknotenWahr`,
`MondknotenMittel`. `longitude` und `latitude` in Grad, `speed` in Grad je Tag (negativ heisst
ruecklaeufig). `lat` ist die geografische Breite (Norden positiv), `lon` die Laenge (Osten
positiv).

Fehler kommen als `{"error": "...", "code": "..."}`: 400 Eingabe, 401 kein Zugriff, 413 Groesse,
415 Format, 422 fachlich nicht rechenbar (`ausserhalb_zeitraum`, `haeuser_nicht_berechenbar`,
`haeusersystem_unbekannt`), 503 ohne gesetzten Token.

## Fachliche Festlegungen

- Tropischer Tierkreis, geozentrisch, scheinbare Staende, Ekliptik des Datums.
- Haeuser nach Placidus. Jenseits des Polarkreises gibt es kein Ergebnis und kein Ersatzsystem,
  sondern den Fehler `haeuser_nicht_berechenbar`.
- `Lilith` ist die mittlere Lilith (mittleres Mondapogaeum), wie bei Swiss Ephemeris auf der
  geneigten Mondbahn gerechnet und auf die Ekliptik projiziert. Gegenueber der unprojizierten
  Formel (Meeus) weicht die Laenge um bis zu sieben Bogenminuten ab, die Breite ist nicht null.
- `MondknotenWahr` ist der wahre (oskulierende), `MondknotenMittel` der mittlere aufsteigende
  Mondknoten.
- Die Umrechnung von UTC nach UT1 macht die Bibliothek an einer Stelle (Schaltsekunden, Delta T
  nach Stephenson, Morrison und Hohenkerk 2016).
- Welcher Planet in welchem Haus steht, rechnet der Kern nicht. Das ist eine fachliche Regel des
  Aufrufers.

## Genauigkeit

Die Tests vergleichen Laenge und Breite von elf Koerpern (Sonne bis Pluto und Chiron) zu sieben
Zeitpunkten zwischen 1900 und 2099 mit JPL Horizons (`tests/referenz.json`, Zeit in TT). Die
groesste Abweichung liegt bei 0,6 Bogensekunden; die Tests verlangen weniger als eine.

Fuer Zeitpunkte in der Zukunft ist Delta T eine Vorhersage. Verschiedene Quellen weichen dort um
Sekunden ab, beim Mond sind das im Jahr 2050 gut eine, im Jahr 2099 rund fuenfzehn Bogensekunden.

Mondknoten, Lilith, Aszendent und MC pruefen die Tests gegen eigene Formeln nach Meeus,
*Astronomical Algorithms*.

## Daten

Der Kern braucht zwei Dateien aus dem Release `data-v4` von libephemeris. Der Bau laedt sie mit
fester Pruefsumme ins Image; der Kern prueft die Summen bei jedem Start noch einmal und rechnet
Vergleichswerte nach. Stimmt etwas nicht, startet er nicht.

| Datei | SHA-256 |
|---|---|
| `base_core.leb2` | `b891de02f82b68346046da67389fd3713aa81ab299287c632cb20cc396397964` |
| `base_asteroids.leb2` | `9364f821f09076db3cd3cfc428379e136a0eea80917af692681be405601652d8` |

Die zweite Datei enthaelt Chiron. Ohne sie wuerde die Bibliothek Chiron mit einer Bahnnaeherung
rechnen, die um Grade danebenliegen kann.

## Bauen, pruefen, starten

```
docker build --build-arg COMMIT=$(git rev-parse HEAD) -t rechenkern .
docker run --rm --network none --read-only --tmpfs /tmp rechenkern python -m unittest discover -s tests
docker run --rm --read-only -p 127.0.0.1:8790:8000 -e KERN_TOKEN=<mindestens 16 Zeichen> rechenkern
```

`KERN_TOKEN` ist die einzige Einstellung. Der Token gehoert in die Umgebung des Dienstes, nie in
dieses Repository. Der Kern ist fuer ein internes Netz gedacht und braucht keine oeffentliche
Adresse.

Ohne Docker: Python ab 3.12, `pip install -r requirements.txt`, die beiden Dateien nach
`<ordner>/leb/` legen, `LIBEPHEMERIS_DATA_DIR=<ordner>` setzen, dann
`python -m unittest discover -s tests` oder `python kern.py` (lauscht auf 127.0.0.1:8790).
