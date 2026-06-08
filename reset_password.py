"""Forgot-password recovery (requires shell access to the box).

Clears the stored credential hash and all sessions. The next time you open the
web UI, the first-login "create password" screen reappears so you can set a new
one.

    docker compose exec wled-runner python reset_password.py
"""
import database

database.init_db()
database.clear_auth()
print("Auth cleared. Reload the web UI to set a new password.")
