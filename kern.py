# Astromandala Rechenkern
# Copyright (C) 2026 Rhein Ahr Digital
# SPDX-License-Identifier: AGPL-3.0-only
#
# Dieses Programm ist freie Software: Sie koennen es unter den Bedingungen der GNU Affero General
# Public License, Version 3, wie von der Free Software Foundation veroeffentlicht, weitergeben
# und/oder aendern. Es wird OHNE JEDE GEWAEHRLEISTUNG bereitgestellt. Den Lizenztext enthaelt die
# Datei LICENSE.
"""Astromandala Rechenkern: Planetenstaende und Haeuser zu einem Zeitpunkt, sonst nichts.

Ein eigenes Programm mit eigener Schnittstelle (HTTP, JSON). Es kennt keine Mitglieder, keine
Orte, keine Zeitzonen und keine Deutungstexte, speichert nichts und schreibt keine Eingaben in
Protokolle. Gerechnet wird mit libephemeris; die Daten liegen im Image, zur Laufzeit ist das Netz
versiegelt.
"""
import hashlib
import hmac
import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

import libephemeris as swe

VERSION = '1.0.0'
QUELLE = 'https://github.com/clintonkraeher/astromandala-rechenkern'
LIZENZ = 'AGPL-3.0-only'

# Datendateien der Bibliothek (Release data-v4), fest mit Pruefsumme. Ohne `base_asteroids.leb2`
# rechnet libephemeris Chiron stillschweigend mit einer Bahnnaeherung, die um Grade danebenliegen
# kann. Deshalb prueft der Kern beide Dateien beim Start und rechnet Vergleichswerte nach.
DATEN = {
    'base_core.leb2': 'b891de02f82b68346046da67389fd3713aa81ab299287c632cb20cc396397964',
    'base_asteroids.leb2': '9364f821f09076db3cd3cfc428379e136a0eea80917af692681be405601652d8',
}

# Reihenfolge und Namen wie im Ergebnisformat des Astromandala-Rechendienstes: zehn Planeten,
# danach die Zusatzpunkte. Lilith ist die mittlere Lilith (mittleres Mondapogaeum).
KOERPER = [
    ('Sun', swe.SUN), ('Moon', swe.MOON), ('Mercury', swe.MERCURY), ('Venus', swe.VENUS),
    ('Mars', swe.MARS), ('Jupiter', swe.JUPITER), ('Saturn', swe.SATURN), ('Uranus', swe.URANUS),
    ('Neptune', swe.NEPTUNE), ('Pluto', swe.PLUTO), ('Chiron', swe.CHIRON),
    ('Lilith', swe.MEAN_APOG), ('MondknotenWahr', swe.TRUE_NODE), ('MondknotenMittel', swe.MEAN_NODE),
]
HAEUSERSYSTEME = {'placidus': b'P'}

# Die Daten reichen von 1850 bis 2150. Der Kern rechnet mit Abstand zu den Raendern.
JAHR_VON, JAHR_BIS = 1900, 2100
HOECHSTENS_ZEITPUNKTE = 500
HOECHSTENS_BYTES = 65536

# Die Bibliothek haelt ihren Zustand je Prozess. Der Kern rechnet deshalb nie gleichzeitig.
SCHLOSS = threading.Lock()

ZEIT_MUSTER = re.compile(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?Z$')


class Problem(Exception):
    def __init__(self, meldung, status=400, code='ungueltige_anfrage'):
        super().__init__(meldung)
        self.status = status
        self.body = {'error': meldung, 'code': code}


def einrichten(datenordner=None):
    """Legt die Bibliothek auf lokale Daten fest: kein Netz, kein Nachladen, keine zweite Quelle."""
    ordner = Path(datenordner or os.environ.get('LIBEPHEMERIS_DATA_DIR', '/daten')) / 'leb'
    for datei, soll in DATEN.items():
        pfad = ordner / datei
        if not pfad.is_file():
            raise RuntimeError('Datendatei fehlt: ' + datei)
        if hashlib.sha256(pfad.read_bytes()).hexdigest() != soll:
            raise RuntimeError('Datendatei hat nicht die erwartete Pruefsumme: ' + datei)
    swe.set_network_policy('sealed')
    swe.set_auto_spk_download(False)
    swe.set_iers_delta_t_enabled(False)
    swe.set_calc_mode('leb')
    swe.set_precision_tier('base')


def abstand(a, b):
    """Kleinster Winkelabstand in Bogensekunden."""
    return abs((a - b + 180) % 360 - 180) * 3600


# Vergleichswerte von JPL Horizons (scheinbare geozentrische Laenge, Ekliptik des Datums, Zeit in
# TT; Abruf am 20.11.2026). Mehr davon in tests/referenz.json.
SELBSTTEST = [
    (swe.SUN, (2000, 1, 1, 12.0), 280.3681519),
    (swe.MOON, (2000, 1, 1, 12.0), 223.3148557),
    (swe.CHIRON, (1900, 3, 1, 0.0), 264.0555117),
    (swe.CHIRON, (2099, 12, 31, 23.0), 241.8549341),
]


def selbsttest():
    """Rechnet feste Werte nach. Weicht einer um mehr als zwei Bogensekunden ab, startet der Kern
    nicht: lieber kein Ergebnis als ein falsches."""
    for koerper, (jahr, monat, tag, stunde), soll in SELBSTTEST:
        ist = swe.calc(swe.julday(jahr, monat, tag, stunde), koerper, swe.FLG_SPEED)[0][0]
        if abstand(ist, soll) > 2:
            raise RuntimeError('Selbsttest fehlgeschlagen: Koerper %s liegt %.1f Bogensekunden daneben'
                               % (koerper, abstand(ist, soll)))


def zeitpunkt(wert):
    """ISO 8601 in UTC (`2026-11-20T12:00:00Z`) zum julianischen Datum in UT1."""
    treffer = ZEIT_MUSTER.match(wert) if isinstance(wert, str) else None
    if not treffer:
        raise Problem('Zeitpunkte bitte in UTC angeben, zum Beispiel 2026-11-20T12:00:00Z.')
    jahr, monat, tag, stunde, minute = (int(x) for x in treffer.groups()[:5])
    sekunde = int(treffer.group(6) or 0)
    try:
        datetime(jahr, monat, tag, stunde, minute, sekunde, tzinfo=timezone.utc)
    except ValueError:
        raise Problem('Diesen Zeitpunkt gibt es nicht: ' + wert)
    if not JAHR_VON <= jahr <= JAHR_BIS:
        raise Problem('Der Kern rechnet von %d bis %d.' % (JAHR_VON, JAHR_BIS), 422, 'ausserhalb_zeitraum')
    # Eine Stelle fuer die Zeitumrechnung: UTC nach UT1 macht die Bibliothek (Schaltsekunden und
    # Delta T nach Stephenson, Morrison und Hohenkerk 2016).
    return swe.utc_to_jd(jahr, monat, tag, stunde, minute, float(sekunde))[1]


def zahl(wert, minimum, maximum, meldung):
    if isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert) \
            or not minimum <= wert <= maximum:
        raise Problem(meldung)
    return float(wert)


def staende(jd):
    """Scheinbare geozentrische Staende, tropisch, Ekliptik des Datums."""
    liste = []
    for name, koerper in KOERPER:
        werte = swe.calc_ut(jd, koerper, swe.FLG_SPEED)[0]
        laenge, breite, tempo = werte[0] % 360, werte[1], werte[3]
        if not all(math.isfinite(x) for x in (laenge, breite, tempo)):
            raise Problem('Die Berechnung hat kein gueltiges Ergebnis geliefert.', 500, 'rechenfehler')
        liste.append({'name': name, 'longitude': round(laenge, 7), 'latitude': round(breite, 7),
                      'speed': round(tempo, 7)})
    return liste


def himmel(daten):
    zeiten = daten.get('zeitpunkte')
    if not isinstance(zeiten, list) or not 1 <= len(zeiten) <= HOECHSTENS_ZEITPUNKTE:
        raise Problem('Bitte 1 bis %d Zeitpunkte angeben.' % HOECHSTENS_ZEITPUNKTE)
    tage = [(wert, zeitpunkt(wert)) for wert in zeiten]
    with SCHLOSS:
        return {'himmel': [{'zeitpunkt': wert, 'koerper': staende(jd)} for wert, jd in tage]}


def radix(daten):
    jd = zeitpunkt(daten.get('zeitpunkt'))
    breite = zahl(daten.get('lat'), -90, 90, 'Bitte die geografische Breite pruefen.')
    laenge = zahl(daten.get('lon'), -180, 180, 'Bitte die geografische Laenge pruefen.')
    system = daten.get('haeuser', 'placidus')
    if system not in HAEUSERSYSTEME:
        raise Problem('Dieses Haeusersystem rechnet der Kern nicht.', 422, 'haeusersystem_unbekannt')
    with SCHLOSS:
        koerper = staende(jd)
        try:
            spitzen, achsen = swe.houses(jd, breite, laenge, HAEUSERSYSTEME[system])
        except swe.PolarCircleError:
            # Kein stiller Wechsel auf ein anderes Haeusersystem.
            raise Problem('In dieser Breite lassen sich die Haeuser nach Placidus nicht berechnen.',
                          422, 'haeuser_nicht_berechenbar')
    if len(spitzen) != 12 or not all(math.isfinite(x) for x in list(spitzen) + [achsen[0], achsen[1]]):
        raise Problem('Die Berechnung hat kein gueltiges Ergebnis geliefert.', 500, 'rechenfehler')
    return {'zeitpunkt': daten['zeitpunkt'], 'koerper': koerper, 'haeusersystem': system,
            'haeuser': [round(x % 360, 7) for x in spitzen],
            'aszendent': round(achsen[0] % 360, 7), 'mc': round(achsen[1] % 360, 7)}


def quelle():
    """Angebot des Quelltexts (AGPL, Abschnitt 13): Repository und Commit der laufenden Fassung."""
    return {'name': 'Astromandala Rechenkern', 'version': VERSION, 'lizenz': LIZENZ, 'quelle': QUELLE,
            'commit': os.environ.get('KERN_COMMIT', 'unbekannt'),
            'bibliothek': {'name': 'libephemeris', 'version': swe.__version__, 'lizenz': 'AGPL-3.0-only',
                           'quelle': 'https://github.com/g-battaglia/libephemeris'},
            'daten': [{'datei': datei, 'sha256': summe} for datei, summe in DATEN.items()],
            'zeitraum': {'von': JAHR_VON, 'bis': JAHR_BIS}}


class Kern:
    def __init__(self, env=None):
        env = dict(os.environ if env is None else env)
        self.token = env.get('KERN_TOKEN', '')

    def anfrage(self, request):
        if not self.token or len(self.token) < 16:
            raise Problem('Der Rechenkern ist noch nicht eingerichtet.', 503, 'nicht_eingerichtet')
        if not hmac.compare_digest(request.get('HTTP_AUTHORIZATION', '').encode('utf-8', 'replace'),
                                   ('Bearer ' + self.token).encode()):
            raise Problem('Kein Zugriff.', 401, 'kein_zugriff')
        if request.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
            raise Problem('JSON wird erwartet.', 415)
        groesse = int(request.get('CONTENT_LENGTH') or '0')
        if not 0 < groesse <= HOECHSTENS_BYTES:
            raise Problem('Anfrage zu gross oder leer.', 413)
        daten = json.loads(request['wsgi.input'].read(groesse))
        if not isinstance(daten, dict):
            raise Problem('Ungueltige Anfrage.')
        return daten

    def __call__(self, request, start_response):
        status = 200
        try:
            pfad, methode = request.get('PATH_INFO', '/'), request.get('REQUEST_METHOD', 'GET')
            if pfad == '/health' and methode == 'GET':
                body = {'ok': True, 'eingerichtet': len(self.token) >= 16, 'version': VERSION}
            elif pfad == '/quelle' and methode == 'GET':
                body = quelle()
            elif pfad == '/himmel' and methode == 'POST':
                body = himmel(self.anfrage(request))
            elif pfad == '/radix' and methode == 'POST':
                body = radix(self.anfrage(request))
            else:
                raise Problem('Nicht gefunden.', 404, 'nicht_gefunden')
        except Problem as fehler:
            status, body = fehler.status, fehler.body
        except (ValueError, TypeError, json.JSONDecodeError):
            status, body = 400, {'error': 'Ungueltige Anfrage.', 'code': 'ungueltige_anfrage'}
        except Exception:
            # Keine Eingaben und keine Einzelheiten nach aussen oder ins Protokoll.
            status, body = 500, {'error': 'Die Berechnung ist fehlgeschlagen.', 'code': 'rechenfehler'}
        roh = json.dumps(body, ensure_ascii=True, allow_nan=False).encode()
        start_response(str(status) + ' ' + HTTPStatus(status).phrase,
                       [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(roh))),
                        ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')])
        return [roh]


einrichten()
selbsttest()
application = Kern()

if __name__ == '__main__':
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    class Still(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    # Nur fuer die lokale Entwicklung; im Betrieb startet Gunicorn `kern:application`.
    make_server('127.0.0.1', int(os.environ.get('PORT', '8790')), application, handler_class=Still).serve_forever()
