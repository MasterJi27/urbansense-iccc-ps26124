# deploy

| Folder | What | How |
| --- | --- | --- |
| `azure/` | Builds the zip that goes to Azure App Service. Does not deploy. | `deploy\azure\package-azure.bat`, then follow `docs/DEPLOYMENT.md` |
| `windows/` | `SadakSaarthi.exe`: a double-click launcher for the local app. Source is `windows/launcher/SadakSaarthi.cs`. | `deploy\windows\build-exe.bat` writes `SadakSaarthi.exe` to the repo root |

The exe needs the project folder around it (`backend\.venv` and `backend\static_dash`). It is a launcher, not an installer.
Windows SmartScreen may warn the first time because the file is not signed. Choose "More info", then "Run anyway".
