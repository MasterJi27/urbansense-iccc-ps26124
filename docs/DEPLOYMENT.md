# Deployment and production checklist

How SadakSaarthi gets onto Azure, what the host needs, and what to switch before real use. Nothing here deploys by itself.

## 1. Build the package

```bat
deploy\azure\package-azure.bat
```

Builds the dashboard into `backend\static_dash`, runs the backend tests (it stops if one fails), and writes
`dist\azure\sadaksaarthi-api-<time>.zip` with a `.sha256` file. The zip root is the contents of `backend/`:
`app/`, `alembic/`, `static_dash/` (the built UI and `/field`), `models/road_damage/metrics.json`, `requirements.txt`.
`.env`, `*.db`, `.venv` and `tests` are never included, and the script refuses to write the zip if one slips in.
The zip also carries `build_info.json` (build time and git commit) so you can tell which build is live.

## 2. Deploy it

```powershell
az webapp deploy --resource-group rg-urbansense --name app-urbansense-yngmbk --src-path dist\azure\<the zip> --type zip
# or let azd package and deploy by itself (it runs scripts/package-dashboard.ps1 first):
azd deploy api
```

Do not change App Settings while a deploy is running. The Oryx build restarts and the site answers 503 until it ends.

## 3. What the host is (from `infra/modules/resources.bicep`)

| Item | Value |
| --- | --- |
| Service | Azure App Service on Linux, plan B3, Always On |
| Runtime | `PYTHON\|3.12` |
| Startup command | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Build | `SCM_DO_BUILD_DURING_DEPLOYMENT=true`: Azure installs `requirements.txt` |
| Secrets | `SECRET_KEY` and `DATABASE_URL` come from Key Vault references |
| Other settings | `APP_ENV=production`, `DEMO_SEED_ON_START=true`, `DEMO_API_ENABLED=true` |

## 4. Production settings

| Setting | What it does | Production value |
| --- | --- | --- |
| `APP_ENV` | `production` turns off `/docs`, `/redoc`, `/openapi.json` and the CORS regex | `production` |
| `SECRET_KEY` | Signs the JWTs. The app refuses to start outside development if it is the demo default | long random value in Key Vault |
| `DATABASE_URL` | Use PostgreSQL. In production the app now **stops** if it cannot reach the database. It no longer falls back to a local SQLite file (that fallback is development only) | Key Vault reference |
| `CORS_ORIGINS` | Allowed browser origins | the site's own https origin |
| `PUBLIC_BASE_URL` | Base URL used in links and QR codes | the site's https URL |
| `EVIDENCE_DIR` or `AZURE_STORAGE_*` | Where evidence images go. A folder inside the deployed app can be replaced by the next deploy | Blob storage |
| `TRUSTED_PROXY_HOPS` | Reverse proxies in front of the app. Unset means 1 outside development | leave unset on App Service |
| `MAP_TILE_URL`, `MAP_TILE_PROVIDER`, `MAP_TILE_ATTRIBUTION` | Tiles from any provider through the server-side proxy. The key inside the URL stays on the server. Optional: unset means OpenStreetMap in the browser. Do not rely on OSM for a public site (its policy forbids heavy use) | a provider key in Key Vault, if you want your own tiles |
| `DPDP_RETENTION_DAYS` | Evidence retention | 30 (default) |

### Demo switches (read this before real users)

The Bicep sets `DEMO_SEED_ON_START=true` and `DEMO_API_ENABLED=true`. That suits the jury host, but it means:

- The four seeded accounts (`superadmin@`, `admin@`, `inspector@`, `operator@urbansense.local`) exist with the password that is
  written in `backend/app/seed.py` and in the README. Anyone who reads the repository knows it.
- `POST /demo/jury-run` (admin only) can write demo events into the live database.

For anything beyond the jury demo: set both to `false` and replace the seeded accounts and their passwords before the
site gets real users. These two values are in `infra/modules/resources.bicep` (about lines 169 and 184).

## 5. After a deploy

1. `https://<app>.azurewebsites.net/health` returns `status: ok` and `rdd: REAL`.
2. `https://<app>.azurewebsites.net/weights/manifest.json` shows `imgsz: 640`.
3. Sign in and open the dashboard. Open `/field` on a phone.
4. Roll back by deploying the previous zip from `dist\azure\`. Keep the last few.

## 6. Cost

Stop the resource group `rg-urbansense` after a demo, or student credits drain. A stopped App Service answers every
request with `403 - This web app is stopped`.

## 7. What is not covered yet

- No load test, no penetration test and no dependency audit were run.
- The road-damage model has not been measured on real windshield video. The honest clean score is in
  `ml/models/road_damage/EVAL.md`.
- There is no WAF and no Azure Front Door in `infra/`.
