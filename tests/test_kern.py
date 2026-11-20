# Astromandala Rechenkern
# Copyright (C) 2026 Rhein Ahr Digital
# SPDX-License-Identifier: AGPL-3.0-only
"""Tests des Rechenkerns. Laufen ohne Netz gegen die Datendateien in LIBEPHEMERIS_DATA_DIR."""
import io
import json
import math
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kern
from kern import Kern, abstand, swe

TOKEN = 'nur-fuer-tests-kein-geheimnis'
REFERENZ = json.loads((Path(__file__).parent / 'referenz.json').read_text())
NAMEN = [name for name, _ in kern.KOERPER]


def ruf(pfad, daten=None, methode=None, token=TOKEN, env=None, typ='application/json', roh=None):
    app = Kern({'KERN_TOKEN': TOKEN} if env is None else env)
    body = roh if roh is not None else (json.dumps(daten).encode() if daten is not None else b'')
    request = {'PATH_INFO': pfad, 'REQUEST_METHOD': methode or ('POST' if daten is not None or roh is not None else 'GET'),
               'CONTENT_TYPE': typ, 'CONTENT_LENGTH': str(len(body)), 'wsgi.input': io.BytesIO(body)}
    if token:
        request['HTTP_AUTHORIZATION'] = 'Bearer ' + token
    antwort = {}

    def start(status, kopf):
        antwort['status'], antwort['kopf'] = int(status.split()[0]), dict(kopf)

    teile = app(request, start)
    return antwort['status'], json.loads(b''.join(teile)), antwort['kopf']


def julday_tt(zeit):
    jahr, monat, tag = (int(x) for x in zeit[:10].split('-'))
    stunde, minute = (int(x) for x in zeit[11:].split(':'))
    return swe.julday(jahr, monat, tag, stunde + minute / 60)


class ReferenzTests(unittest.TestCase):
    """Unabhaengiger Vergleich mit JPL Horizons, 1900 bis 2099."""

    def test_laengen_und_breiten_gegen_horizons(self):
        nummern = dict(kern.KOERPER)
        for name, werte in REFERENZ['koerper'].items():
            for zeit, (laenge, breite) in zip(REFERENZ['zeitpunkte'], werte):
                with self.subTest(koerper=name, zeit=zeit):
                    ist = swe.calc(julday_tt(zeit), nummern[name], swe.FLG_SPEED)[0]
                    self.assertLess(abstand(ist[0], laenge), 1.0)
                    self.assertLess(abs(ist[1] - breite) * 3600, 1.0)

    def test_alle_elf_koerper_sind_in_der_referenz(self):
        self.assertEqual(sorted(REFERENZ['koerper']), sorted(NAMEN[:11]))
        self.assertEqual(len(REFERENZ['zeitpunkte']), 7)

    def test_mondknoten_und_lilith(self):
        # 14.07.1978, 05:40 UT: Mondknoten nach Swiss Ephemeris (wahrer 29 Grad 16 Minuten
        # Jungfrau, mittlerer 0 Grad 16 Minuten Waage), auf die Bogenminute.
        status, body, _ = ruf('/himmel', {'zeitpunkte': ['1978-07-14T05:40:00Z']})
        self.assertEqual(status, 200)
        staende = {k['name']: k for k in body['himmel'][0]['koerper']}
        self.assertLess(abstand(staende['MondknotenWahr']['longitude'], 179 + 16.5 / 60), 60)
        self.assertLess(abstand(staende['MondknotenMittel']['longitude'], 180 + 16.5 / 60), 60)
        # Mittlere Lilith und mittlerer Knoten nach Meeus, Astronomical Algorithms, Kap. 47.
        jd = swe.julday(1978, 7, 14, 5 + 40 / 60)
        t = (jd - 2451545.0) / 36525
        perigaeum = 83.3532465 + 4069.0137287 * t - 0.0103200 * t ** 2 - t ** 3 / 80053 + t ** 4 / 18999000
        knoten = 125.0445479 - 1934.1362891 * t + 0.0020754 * t ** 2 + t ** 3 / 467441 - t ** 4 / 60616000
        # Die Bibliothek gibt die mittlere Lilith wie Swiss Ephemeris an: auf der geneigten Mondbahn
        # gerechnet und auf die Ekliptik projiziert. Gegenueber dem unprojizierten Wert sind das bis
        # zu sieben Bogenminuten; die Breite ist deshalb nicht null.
        u, neigung = math.radians(perigaeum + 180 - knoten), math.radians(5.1453964)
        projiziert = (knoten + math.degrees(math.atan2(math.sin(u) * math.cos(neigung), math.cos(u)))) % 360
        self.assertLess(abstand(staende['Lilith']['longitude'], projiziert), 30)
        self.assertAlmostEqual(staende['Lilith']['latitude'],
                               math.degrees(math.asin(math.sin(u) * math.sin(neigung))), delta=0.01)
        self.assertLess(abstand(staende['MondknotenMittel']['longitude'], knoten % 360), 60)
        self.assertLess(staende['MondknotenMittel']['speed'], 0)

    def test_aszendent_und_mc_gegen_eigene_formel(self):
        # Eigene Rechnung nach Meeus (mittlere Sternzeit, mittlere Schiefe). Ohne Nutation, deshalb
        # eine Toleranz von einer Bogenminute; ein vertauschtes Vorzeichen fiele um Grade auf.
        for zeit, breite, laenge in (('1978-07-14T05:40:00Z', 47.0707, 15.4395),
                                     ('2000-01-01T12:00:00Z', 47.43, 9.66),
                                     ('2026-11-20T00:00:00Z', -33.87, 151.21),
                                     ('1950-06-15T12:00:00Z', 40.71, -74.01)):
            with self.subTest(zeit=zeit):
                status, body, _ = ruf('/radix', {'zeitpunkt': zeit, 'lat': breite, 'lon': laenge})
                self.assertEqual(status, 200)
                jd = kern.zeitpunkt(zeit)
                t = (jd - 2451545.0) / 36525
                sternzeit = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t ** 2 + laenge) % 360
                schiefe = math.radians(23.4392911 - 0.0130042 * t)
                ramc, phi = math.radians(sternzeit), math.radians(breite)
                mc = math.degrees(math.atan2(math.sin(ramc), math.cos(ramc) * math.cos(schiefe))) % 360
                asz = math.degrees(math.atan2(math.cos(ramc), -(math.sin(ramc) * math.cos(schiefe)
                                                                + math.tan(phi) * math.sin(schiefe)))) % 360
                self.assertLess(abstand(body['mc'], mc), 60)
                self.assertLess(abstand(body['aszendent'], asz), 60)
                self.assertEqual(len(body['haeuser']), 12)
                self.assertLess(abstand(body['haeuser'][0], body['aszendent']), 0.01)
                self.assertLess(abstand(body['haeuser'][9], body['mc']), 0.01)
                self.assertLess(abstand(body['haeuser'][6], (body['aszendent'] + 180) % 360), 0.01)


class HimmelTests(unittest.TestCase):
    def test_vierzehn_koerper_in_fester_reihenfolge(self):
        status, body, kopf = ruf('/himmel', {'zeitpunkte': ['2026-11-20T12:00:00Z']})
        self.assertEqual(status, 200)
        self.assertEqual(kopf['Cache-Control'], 'no-store')
        koerper = body['himmel'][0]['koerper']
        self.assertEqual([k['name'] for k in koerper], NAMEN)
        self.assertEqual(NAMEN[:10], ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn',
                                      'Uranus', 'Neptune', 'Pluto'])
        for k in koerper:
            self.assertTrue(0 <= k['longitude'] < 360)
            self.assertTrue(math.isfinite(k['speed']))
        self.assertGreater(koerper[0]['speed'], 0.9)   # Sonne rund ein Grad je Tag
        self.assertGreater(koerper[1]['speed'], 11)    # Mond

    def test_zukunft_und_viele_tage(self):
        tage = ['2027-%02d-%02dT12:00:00Z' % (monat, tag) for monat in range(1, 13) for tag in range(1, 29)]
        status, body, _ = ruf('/himmel', {'zeitpunkte': tage})
        self.assertEqual(status, 200)
        self.assertEqual([h['zeitpunkt'] for h in body['himmel']], tage)
        sonne = [h['koerper'][0]['longitude'] for h in body['himmel']]
        self.assertTrue(all(0 < (b - a) % 360 < 5 for a, b in zip(sonne, sonne[1:])))

    def test_ruecklaeufigkeit_aus_dem_tempo(self):
        # Merkur ist vom 9. bis 29. November 2026 nicht durchgehend ruecklaeufig; geprueft wird nur,
        # dass das Tempo zur Bewegung zwischen zwei Tagen passt.
        status, body, _ = ruf('/himmel', {'zeitpunkte': ['2026-03-01T00:00:00Z', '2026-03-02T00:00:00Z']})
        a, b = (h['koerper'][2] for h in body['himmel'])
        bewegung = (b['longitude'] - a['longitude'] + 180) % 360 - 180
        self.assertEqual(bewegung < 0, a['speed'] < 0)
        self.assertAlmostEqual(bewegung, (a['speed'] + b['speed']) / 2, delta=0.05)

    def test_eingaben(self):
        for daten in ({}, {'zeitpunkte': []}, {'zeitpunkte': 'heute'}, {'zeitpunkte': ['2026-11-20']},
                      {'zeitpunkte': ['2026-11-20T12:00:00+01:00']}, {'zeitpunkte': ['2026-02-30T12:00:00Z']},
                      {'zeitpunkte': ['2026-11-20T25:00:00Z']}, {'zeitpunkte': [20261120]},
                      {'zeitpunkte': ['2026-11-20T12:00:00Z'] * 501}):
            with self.subTest(daten=str(daten)[:60]):
                status, body, _ = ruf('/himmel', daten)
                self.assertEqual(status, 400)
                self.assertIn('error', body)
        self.assertEqual(ruf('/himmel', {'zeitpunkte': ['2026-11-20T12:00Z']})[0], 200)

    def test_zeitraum(self):
        for zeit in ('1899-12-31T23:59:59Z', '2101-01-01T00:00:00Z'):
            status, body, _ = ruf('/himmel', {'zeitpunkte': [zeit]})
            self.assertEqual((status, body['code']), (422, 'ausserhalb_zeitraum'))
        for zeit in ('1900-01-01T00:00:00Z', '2100-12-31T23:59:59Z'):
            self.assertEqual(ruf('/himmel', {'zeitpunkte': [zeit]})[0], 200)

    def test_gleichzeitige_anfragen_liefern_dasselbe(self):
        tage = ['2026-%02d-15T12:00:00Z' % monat for monat in range(1, 13)]
        soll = ruf('/himmel', {'zeitpunkte': tage})[1]
        abweichend = []

        def lauf():
            for _ in range(5):
                if ruf('/himmel', {'zeitpunkte': tage})[1] != soll:
                    abweichend.append(1)
                ruf('/radix', {'zeitpunkt': tage[3], 'lat': 48.2, 'lon': 16.37})

        faeden = [threading.Thread(target=lauf) for _ in range(6)]
        for faden in faeden:
            faden.start()
        for faden in faeden:
            faden.join()
        self.assertEqual(abweichend, [])


class RadixTests(unittest.TestCase):
    def test_radix(self):
        status, body, _ = ruf('/radix', {'zeitpunkt': '1978-07-14T05:40:00Z', 'lat': 47.0707, 'lon': 15.4395})
        self.assertEqual(status, 200)
        self.assertEqual(body['haeusersystem'], 'placidus')
        self.assertEqual([k['name'] for k in body['koerper']], NAMEN)
        self.assertEqual(int(body['aszendent'] // 30), 4)   # Loewe
        self.assertEqual(int(body['mc'] // 30), 1)          # Stier
        spitzen = body['haeuser']
        self.assertTrue(all(0 < (b - a) % 360 < 90 for a, b in zip(spitzen, spitzen[1:] + spitzen[:1])))

    def test_polare_breite_ohne_ersatzsystem(self):
        status, body, _ = ruf('/radix', {'zeitpunkt': '2000-01-01T12:00:00Z', 'lat': 78.22, 'lon': 15.65})
        self.assertEqual((status, body['code']), (422, 'haeuser_nicht_berechenbar'))
        self.assertNotIn('haeuser', body)

    def test_eingaben(self):
        gut = {'zeitpunkt': '2000-01-01T12:00:00Z', 'lat': 47.0, 'lon': 15.0}
        for aenderung in ({'lat': 91}, {'lat': '47'}, {'lat': True}, {'lon': 181}, {'lon': None},
                          {'lat': float('nan')}, {'zeitpunkt': None}, {'zeitpunkt': '2000-01-01 12:00'}):
            with self.subTest(aenderung=aenderung):
                roh = json.dumps(dict(gut, **aenderung)).encode()
                self.assertEqual(ruf('/radix', roh=roh)[0], 400)
        status, body, _ = ruf('/radix', dict(gut, haeuser='koch'))
        self.assertEqual((status, body['code']), (422, 'haeusersystem_unbekannt'))


class ZugangTests(unittest.TestCase):
    ANFRAGE = {'zeitpunkte': ['2026-11-20T12:00:00Z']}

    def test_token(self):
        self.assertEqual(ruf('/himmel', self.ANFRAGE, token='')[0], 401)
        self.assertEqual(ruf('/himmel', self.ANFRAGE, token='falsch')[0], 401)
        self.assertEqual(ruf('/radix', {'zeitpunkt': '2000-01-01T12:00:00Z', 'lat': 1, 'lon': 1}, token='x')[0], 401)

    def test_ohne_oder_mit_zu_kurzem_token_nicht_eingerichtet(self):
        for env in ({}, {'KERN_TOKEN': 'kurz'}):
            status, body, _ = ruf('/himmel', self.ANFRAGE, env=env, token=env.get('KERN_TOKEN', ''))
            self.assertEqual((status, body['code']), (503, 'nicht_eingerichtet'))
            self.assertEqual(ruf('/health', env=env)[1]['eingerichtet'], False)

    def test_format_und_groesse(self):
        self.assertEqual(ruf('/himmel', self.ANFRAGE, typ='text/plain')[0], 415)
        self.assertEqual(ruf('/himmel', roh=b'')[0], 413)
        self.assertEqual(ruf('/himmel', roh=b' ' * 70000)[0], 413)
        self.assertEqual(ruf('/himmel', roh=b'{kein json')[0], 400)
        self.assertEqual(ruf('/himmel', roh=b'[1, 2]')[0], 400)

    def test_pfade(self):
        self.assertEqual(ruf('/')[0], 404)
        self.assertEqual(ruf('/himmel')[0], 404)            # GET
        self.assertEqual(ruf('/health', methode='POST')[0], 404)

    def test_health_und_quelle_ohne_token(self):
        status, body, _ = ruf('/health', token='')
        self.assertEqual((status, body['ok'], body['eingerichtet']), (200, True, True))
        status, body, _ = ruf('/quelle', token='')
        self.assertEqual(status, 200)
        self.assertEqual(body['lizenz'], 'AGPL-3.0-only')
        self.assertTrue(body['quelle'].startswith('https://github.com/'))
        self.assertEqual(body['bibliothek']['version'], swe.__version__)
        self.assertEqual({d['datei'] for d in body['daten']}, set(kern.DATEN))
        self.assertNotIn(TOKEN, json.dumps(body))


class StartTests(unittest.TestCase):
    def test_bibliothek_ist_versiegelt_und_fest_eingestellt(self):
        self.assertEqual(swe.get_network_policy(), 'sealed')
        self.assertEqual(swe.get_calc_mode(), 'leb')
        self.assertEqual(swe.get_precision_tier(), 'base')
        self.assertFalse(swe.get_auto_spk_download())
        self.assertFalse(swe.get_iers_delta_t_enabled())

    def test_fehlende_oder_fremde_daten_verhindern_den_start(self):
        import tempfile
        with tempfile.TemporaryDirectory() as ordner:
            with self.assertRaisesRegex(RuntimeError, 'fehlt'):
                kern.einrichten(ordner)
            (Path(ordner) / 'leb').mkdir()
            for datei in kern.DATEN:
                (Path(ordner) / 'leb' / datei).write_bytes(b'nicht die echte Datei')
            with self.assertRaisesRegex(RuntimeError, 'Pruefsumme'):
                kern.einrichten(ordner)

    def test_selbsttest_erkennt_falsche_werte(self):
        kern.selbsttest()
        echt = kern.SELBSTTEST
        try:
            kern.SELBSTTEST = [(swe.CHIRON, (2000, 1, 1, 12.0), 251.0)]
            with self.assertRaisesRegex(RuntimeError, 'Selbsttest'):
                kern.selbsttest()
        finally:
            kern.SELBSTTEST = echt


if __name__ == '__main__':
    unittest.main()
