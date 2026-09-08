# Local deployment

Run scripts/run_backend.ps1 from Windows PowerShell. It binds to 0.0.0.0:8000 for emulator/LAN access and disables HTTP access logs so precise location query strings are not written. Do not expose this prototype directly to the internet. Public deployment still needs an HTTPS reverse proxy, streaming request-size enforcement, distributed rate limiting, secrets management and production persistence.

Android debug permits local HTTP; release disallows cleartext. Set a real HTTPS backend URL in the release build configuration before distribution. No API keys are compiled into Android. Application data backup is disabled.

Backend dependencies are isolated under backend/.venv. requirements.lock.txt records the versions tested on this machine. Gradle cache and downloaded distribution are under .tools. The Gradle wrapper is from the official Gradle repository. Android local.properties points to this computer's SDK and is ignored by Git.

Test with scripts/test_backend.ps1 and scripts/build_android.ps1. Live verification is optional: from backend, run `.venv/Scripts/python.exe live_check.py`. Ordinary automated tests do not use the network.
