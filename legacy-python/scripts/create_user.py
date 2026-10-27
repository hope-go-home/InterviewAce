"""创建用户：python scripts/create_user.py <username> <password> [--role admin]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interviewace.backend.database.mysql import create_user, get_user_by_username, init_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--role", default="user", choices=["admin", "user"])
    args = parser.parse_args()

    init_db()
    if get_user_by_username(args.username):
        print(f"用户 {args.username} 已存在")
        return
    uid = create_user(args.username, args.password, args.role)
    print(f"创建成功 id={uid} username={args.username} role={args.role}")


if __name__ == "__main__":
    main()
