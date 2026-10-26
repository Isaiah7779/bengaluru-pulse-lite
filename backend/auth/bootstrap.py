"""Create (or promote) the initial administrator — no hard-coded credentials.

    python -m auth.bootstrap --email admin@example.org --name "Ops"
        password read from the BOOTSTRAP_ADMIN_PASSWORD environment variable,
        otherwise prompted on the terminal (never passed as an argument, so it
        does not end up in shell history or process listings).

    python -m auth.bootstrap --email someone@example.org --promote
        promote an existing account (they keep their own password).

Refuses to run if an active administrator already exists, unless --force.
Every use is written to the audit log.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from auth.security import hash_password, password_problems
from db.models import AuditLog, User
from db.session import session_scope


def bootstrap(email: str, name: str, password: str | None, promote: bool, force: bool) -> str:
    email = email.strip().lower()
    with session_scope() as s:
        admins = s.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))).all()
        if admins and not force:
            raise SystemExit(f"Refusing: {len(admins)} active administrator(s) already exist (use --force to add another).")
        user = s.scalar(select(User).where(User.email == email))
        if promote:
            if user is None:
                raise SystemExit("No account with that e-mail; register it first or omit --promote.")
            user.role = "admin"
            user.is_active = True
            action = "promoted"
        else:
            if user is not None:
                raise SystemExit("An account with that e-mail exists; use --promote.")
            if not password:
                raise SystemExit("A password is required.")
            problems = password_problems(password)
            if problems or len(password) < 14:
                raise SystemExit("Admin password must be at least 14 characters and contain " + ", ".join(problems or ["mixed case and a digit"]))
            user = User(email=email, password_hash=hash_password(password), display_name=name, role="admin")
            s.add(user)
            action = "created"
        s.flush()
        s.add(AuditLog(actor_user_id=None, action=f"admin.bootstrap_{action}", target=f"user:{user.id}"))
        return f"Administrator {action}: {email} (id {user.id})"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--promote", action="store_true", help="promote an existing account instead of creating one")
    parser.add_argument("--force", action="store_true", help="allow when an administrator already exists")
    args = parser.parse_args(argv)
    password = None
    if not args.promote:
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
        if not password:
            if not sys.stdin.isatty():
                raise SystemExit("Set BOOTSTRAP_ADMIN_PASSWORD or run interactively.")
            password = getpass.getpass("New admin password: ")
            if password != getpass.getpass("Repeat password: "):
                raise SystemExit("Passwords do not match.")
    print(bootstrap(args.email, args.name, password, args.promote, args.force))


if __name__ == "__main__":
    main()
