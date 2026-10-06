"""Make a newly mounted data directory writable, then drop root before serving."""
import os
import pwd
import sys
from pathlib import Path


def main():
    if os.geteuid() == 0:
        user = pwd.getpwnam("demo")
        data = Path(os.environ.get("BUDGET_DB", "/data/demo.sqlite3")).parent
        data.mkdir(parents=True, exist_ok=True)
        os.chown(data, user.pw_uid, user.pw_gid)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
