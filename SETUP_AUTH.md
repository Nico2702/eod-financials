# GitHub OAuth Setup — Schritt-für-Schritt

## 1. GitHub OAuth App erstellen

1. Gehe zu: https://github.com/settings/developers
2. Klicke **"New OAuth App"**
3. Fülle aus:
   - **Application name**: NaroIX Fundamentals Viewer
   - **Homepage URL**: https://DEIN-APP-NAME.streamlit.app
   - **Authorization callback URL**: https://DEIN-APP-NAME.streamlit.app
     ⚠ Muss exakt mit `redirect_uri` in secrets.toml übereinstimmen
4. Klicke **"Register application"**
5. Notiere **Client ID**
6. Klicke **"Generate a new client secret"** → notiere **Client Secret**

---

## 2. Dateien in dein Repo

Folgende Dateien müssen im Root deines Repos liegen:

```
eod-financials/
├── eodhd_fundamentals.py    ← bereits vorhanden
├── auth.py                  ← NEU
├── requirements.txt         ← aktualisiert
└── .streamlit/
    └── secrets.toml         ← NEU (nicht committen!)
```

---

## 3. secrets.toml befüllen

Erstelle `.streamlit/secrets.toml` (aus `secrets.toml.template`):

```toml
[github_oauth]
client_id     = "abc123..."          # aus Schritt 1
client_secret = "def456..."          # aus Schritt 1
redirect_uri  = "https://dein-app.streamlit.app"
allowed_users = ["nico-username", "anderer-user"]
```

⚠ **secrets.toml niemals committen!**
Füge `.streamlit/secrets.toml` zu `.gitignore` hinzu:
```
.streamlit/secrets.toml
```

---

## 4. Streamlit Cloud Secrets setzen

Da secrets.toml nicht committed wird, musst du die Werte in Streamlit Cloud eintragen:

1. Öffne deine App auf share.streamlit.io
2. Klicke **"⋮"** → **"Settings"** → **"Secrets"**
3. Füge den gesamten Inhalt aus `secrets.toml` ein
4. Klicke **"Save"**

---

## 5. Nutzer freischalten

In `secrets.toml` (und Streamlit Cloud Secrets) einfach den GitHub Username hinzufügen:

```toml
allowed_users = ["nico", "kunde-max", "analyst-jan"]
```

Dann **Redeploy** oder kurz warten — Streamlit Cloud lädt Secrets automatisch neu.

---

## 6. Lokal testen

```bash
# .streamlit/secrets.toml lokal anlegen
# redirect_uri auf http://localhost:8501 setzen (GitHub OAuth App anpassen!)
streamlit run eodhd_fundamentals.py
```

---

## Wie es funktioniert

```
Nutzer öffnet App
    ↓
Nicht eingeloggt → Login-Seite mit "Mit GitHub anmelden" Button
    ↓
Klick → Weiterleitung zu GitHub
    ↓
GitHub fragt: "NaroIX Fundamentals Viewer möchte deinen Account lesen"
    ↓
Nutzer bestätigt → GitHub leitet zurück mit ?code=...
    ↓
App tauscht code gegen Access Token
    ↓
App holt GitHub Username
    ↓
Username in allowed_users? → ✅ Zugang   ❌ Verweigert
```
