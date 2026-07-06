"""Rejestracja natywnego tokenu push (aplikacja Capacitor: FCM/APNs) — monetyzacja Faza 5."""
import models


def _tokeny(db, token):
    return db.query(models.PushDeviceToken).filter_by(token=token).all()


def test_rejestracja_natywnego_tokenu(admin_client, admin, db):
    r = admin_client.post("/api/me/push/register-native",
                          json={"token": "fcm-abc-123", "platform": "android"})
    assert r.status_code == 204
    wpisy = _tokeny(db, "fcm-abc-123")
    assert len(wpisy) == 1
    assert wpisy[0].user_id == admin.id
    assert wpisy[0].platform == "android"


def test_ponowna_rejestracja_tego_samego_tokenu_nie_duplikuje(admin_client, db):
    admin_client.post("/api/me/push/register-native",
                      json={"token": "fcm-dup", "platform": "android"})
    admin_client.post("/api/me/push/register-native",
                      json={"token": "fcm-dup", "platform": "ios"})
    wpisy = _tokeny(db, "fcm-dup")
    assert len(wpisy) == 1
    assert wpisy[0].platform == "ios"   # upsert nadpisał platformę


def test_brak_tokenu_daje_400(admin_client):
    r = admin_client.post("/api/me/push/register-native", json={"platform": "android"})
    assert r.status_code == 400


def test_nieznana_platforma_zapisana_jako_none(admin_client, db):
    r = admin_client.post("/api/me/push/register-native",
                          json={"token": "fcm-xyz", "platform": "windows-phone"})
    assert r.status_code == 204
    assert _tokeny(db, "fcm-xyz")[0].platform is None


def test_rejestracja_wymaga_logowania(client):
    r = client.post("/api/me/push/register-native", json={"token": "t", "platform": "ios"})
    assert r.status_code in (401, 403)
