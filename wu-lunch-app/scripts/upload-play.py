#!/usr/bin/env python3
"""App-Bundle in den internen Test von Google Play hochladen (Google Play Developer API v3).

Aufruf im Workflow „WU Lunch Android APK":
    python scripts/upload-play.py --check              # nur Zugang prüfen, nichts ändern
    python scripts/upload-play.py pfad/zur/datei.aab   # hochladen und im internen Test bereitstellen
    python scripts/upload-play.py --screenshots        # Smartphone-Screenshots des Store-Eintrags ersetzen

Zugang: Dienstkonto-Schlüssel (JSON) im Secret PLAY_SERVICE_ACCOUNT_JSON. Der Schlüssel wird nur an Googles
Anmeldebibliothek übergeben und nie ausgegeben. Das Dienstkonto braucht in der Play Console nur das Recht,
Releases für Test-Tracks zu verwalten.

Ablauf beim Hochladen (ein „Edit" ist Googles Entwurf, der erst mit commit wirksam wird):
  Edit anlegen -> Bundle hochladen -> Track „internal" auf die neue Version setzen -> commit.
Solange die App bei Google noch im Entwurf ist, lehnt Google fertige Releases ab („Only releases with status
draft may be created on draft app"). Dann wird derselbe Ablauf als Entwurf wiederholt; die Einführung
bestätigt der Betreiber einmal in der Play Console.
"""
import json
import os
import sys
from pathlib import Path

PACKAGE = 'at.startit.wufood'
TRACK = 'internal'
API = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/' + PACKAGE
UPLOAD = 'https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/' + PACKAGE
ROOT = Path(__file__).resolve().parents[1]


class PlayError(Exception):
    """Fehler mit verständlicher Erklärung; enthält nie Zugangsdaten."""


def explain(response, step):
    try:
        message = response.json().get('error', {}).get('message', '')
    except Exception:
        message = ''
    hint = ''
    if response.status_code in (401, 403):
        hint = (' Das Dienstkonto hat in der Play Console keinen Zugriff auf die App oder nicht das Recht,'
                ' Releases für Test-Tracks zu verwalten.')
    elif response.status_code == 404:
        hint = (' Google kennt das Paket ' + PACKAGE + ' für dieses Konto nicht. Der allererste Upload einer App'
                ' muss einmal von Hand in der Play Console erfolgen.')
    if 'already been used' in message:
        hint = ' Diese Versionsnummer liegt schon bei Google Play. Für einen neuen Upload braucht es einen neuen Build.'
    return PlayError(f'{step} fehlgeschlagen (HTTP {response.status_code}): {message[:300]}{hint}')


def call(session, method, url, step, **kwargs):
    response = session.request(method, url, timeout=kwargs.pop('timeout', 120), **kwargs)
    if response.status_code >= 300:
        raise explain(response, step)
    return response.json() if response.content else {}


def release_notes(path=None):
    """Versionshinweise je Sprache aus store-listing/release-notes.json (höchstens 500 Zeichen je Sprache)."""
    path = path or ROOT / 'store-listing/release-notes.json'
    notes = json.loads(Path(path).read_text(encoding='utf-8'))
    result = []
    for language, text in notes.items():
        text = str(text).strip()
        if not text:
            continue
        if len(text) > 500:
            raise PlayError(f'Versionshinweise für {language} sind länger als 500 Zeichen.')
        result.append({'language': language, 'text': text})
    return result


def check(session):
    """Zugang prüfen, ohne etwas zu ändern: Entwurf anlegen, Track lesen, Entwurf verwerfen."""
    edit = call(session, 'POST', API + '/edits', 'Zugang prüfen')['id']
    try:
        track = call(session, 'GET', f'{API}/edits/{edit}/tracks/{TRACK}', 'Internen Test lesen')
    finally:
        session.request('DELETE', f'{API}/edits/{edit}', timeout=60)
    releases = track.get('releases', [])
    codes = sorted({int(code) for release in releases for code in release.get('versionCodes', [])})
    return {'track': TRACK, 'releases': [{'name': r.get('name'), 'status': r.get('status')} for r in releases],
            'versionCodes': codes}


def upload_once(session, bundle, name, notes, status):
    edit = call(session, 'POST', API + '/edits', 'Entwurf anlegen')['id']
    with open(bundle, 'rb') as handle:
        uploaded = call(session, 'POST', f'{UPLOAD}/edits/{edit}/bundles?uploadType=media', 'App-Bundle hochladen',
                        data=handle, headers={'Content-Type': 'application/octet-stream'}, timeout=900)
    code = int(uploaded['versionCode'])
    release = {'name': name, 'versionCodes': [str(code)], 'status': status}
    if notes:
        release['releaseNotes'] = notes
    call(session, 'PUT', f'{API}/edits/{edit}/tracks/{TRACK}', 'Internen Test aktualisieren',
         json={'track': TRACK, 'releases': [release]})
    try:
        call(session, 'POST', f'{API}/edits/{edit}:commit', 'Änderung bestätigen')
    except PlayError as error:
        # Manche Konten verlangen, dass Änderungen nicht automatisch zur Prüfung gehen. Der interne Test
        # braucht keine Prüfung; offene Änderungen sendet der Betreiber in der Play Console selbst ab.
        if 'changesNotSentForReview' not in str(error):
            raise
        call(session, 'POST', f'{API}/edits/{edit}:commit?changesNotSentForReview=true', 'Änderung bestätigen')
    return {'versionCode': code, 'status': status, 'track': TRACK, 'name': name}


def upload(session, bundle, name, notes):
    """Erst als fertigen Release versuchen; verlangt Google bei einer Entwurfs-App einen Entwurf, so wiederholen."""
    try:
        return upload_once(session, bundle, name, notes, 'completed')
    except PlayError as error:
        if 'draft' not in str(error).lower():
            raise
        return upload_once(session, bundle, name, notes, 'draft')


def upload_screenshots(session, folder=None):
    """Smartphone-Screenshots im Store-Eintrag ersetzen – je Sprache des Eintrags die Dateien
    store-listing/screenshot-<de|en>-<nr>.png. Erst wenn alle Bilder hochgeladen sind, wird bestätigt;
    scheitert ein Schritt, wird Googles Entwurf verworfen und der Store-Eintrag bleibt, wie er war."""
    folder = Path(folder or ROOT / 'store-listing')
    edit = call(session, 'POST', API + '/edits', 'Entwurf anlegen')['id']
    try:
        listings = call(session, 'GET', f'{API}/edits/{edit}/listings', 'Store-Einträge lesen').get('listings', [])
        done = {}
        for listing in listings:
            language = listing['language']
            files = sorted(folder.glob(f"screenshot-{language.split('-')[0].lower()}-*.png"))
            if not files:
                continue
            if not 2 <= len(files) <= 8:
                raise PlayError(f'Google Play verlangt 2 bis 8 Smartphone-Screenshots je Sprache; für {language} liegen {len(files)} vor.')
            images = f'{API}/edits/{edit}/listings/{language}/phoneScreenshots'
            call(session, 'DELETE', images, 'Bisherige Screenshots entfernen')
            for file in files:
                with open(file, 'rb') as handle:
                    call(session, 'POST', f'{UPLOAD}/edits/{edit}/listings/{language}/phoneScreenshots?uploadType=media',
                         'Screenshot hochladen', data=handle, headers={'Content-Type': 'image/png'}, timeout=300)
            done[language] = len(files)
        if not done:
            raise PlayError('Der Store-Eintrag hat keine Sprache, für die Screenshots im Projekt liegen (Deutsch oder Englisch).')
        try:
            call(session, 'POST', f'{API}/edits/{edit}:commit', 'Änderung bestätigen')
            sent = True
        except PlayError as error:
            if 'changesNotSentForReview' not in str(error):
                raise
            call(session, 'POST', f'{API}/edits/{edit}:commit?changesNotSentForReview=true', 'Änderung bestätigen')
            sent = False
    except PlayError as error:
        session.request('DELETE', f'{API}/edits/{edit}', timeout=60)
        if 'HTTP 403' in str(error) or 'HTTP 401' in str(error):
            raise PlayError(str(error) + ' Für den Store-Eintrag braucht das Dienstkonto in der Play Console zusätzlich'
                            ' das Recht „Store-Präsenz verwalten".') from None
        raise
    return {'screenshots': done, 'sentForReview': sent}


def session_from_env():
    raw = os.environ.get('PLAY_SERVICE_ACCOUNT_JSON', '').strip()
    if not raw:
        raise PlayError('Secret PLAY_SERVICE_ACCOUNT_JSON fehlt (siehe Anleitung „Automatischer Play-Upload").')
    try:
        info = json.loads(raw)
    except ValueError:
        raise PlayError('PLAY_SERVICE_ACCOUNT_JSON ist kein gültiges JSON. Bitte den gesamten Inhalt der'
                        ' heruntergeladenen Schlüsseldatei einfügen.') from None
    if info.get('type') != 'service_account' or not info.get('client_email'):
        raise PlayError('PLAY_SERVICE_ACCOUNT_JSON ist kein Dienstkonto-Schlüssel (Feld "type" muss'
                        ' "service_account" sein).')
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=['https://www.googleapis.com/auth/androidpublisher'])
    return AuthorizedSession(credentials), info['client_email']


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        session, account = session_from_env()
        print('Dienstkonto:', account)
        if argv[1] == '--check':
            result = check(session)
            print('Zugang funktioniert. Interner Test derzeit:', json.dumps(result, ensure_ascii=False))
            return 0
        if argv[1] == '--screenshots':
            result = upload_screenshots(session)
            print('Screenshots ersetzt:', json.dumps(result, ensure_ascii=False))
            summary = os.environ.get('GITHUB_STEP_SUMMARY')
            if summary:
                ending = ('Die Änderung ist zur Prüfung an Google gesendet.' if result['sentForReview'] else
                          'Bitte in der Play Console unter „Übersicht über die Veröffentlichung" einmal zur Prüfung senden.')
                with open(summary, 'a', encoding='utf-8') as handle:
                    handle.write(f"### Google Play: Screenshots im Store-Eintrag ersetzt\n\n{json.dumps(result['screenshots'])}\n\n{ending}\n")
            return 0
        bundle = Path(argv[1])
        if not bundle.is_file():
            raise PlayError(f'App-Bundle {bundle} fehlt. Es entsteht nur mit eingerichtetem Upload-Schlüssel.')
        version = json.loads((ROOT / 'app.json').read_text(encoding='utf-8'))['expo']['version']
        result = upload(session, bundle, version, release_notes())
        print('Hochgeladen:', json.dumps(result, ensure_ascii=False))
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            ending = ('Für Tester verfügbar.' if result['status'] == 'completed' else
                      'Als Entwurf angelegt: bitte in der Play Console unter „Interne Tests" einmal einführen.')
            with open(summary, 'a', encoding='utf-8') as handle:
                handle.write(f"### Google Play: Version {version} ({result['versionCode']}) im internen Test\n\n{ending}\n")
        return 0
    except PlayError as error:
        print('::error::' + str(error))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
