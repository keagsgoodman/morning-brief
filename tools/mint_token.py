"""
Run this ONCE on your own computer to turn your Garmin password into a
long-lived token. The token is what goes into the GitHub secret - your
password never leaves this machine.

    pip install garminconnect
    python tools/mint_token.py
"""

import getpass
import sys


def main():
    try:
        from garminconnect import Garmin
    except ImportError:
        print("Run:  pip install garminconnect", file=sys.stderr)
        return 1

    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (not echoed): ")

    api = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    api.login()
    token = api.client.dumps()

    with open("garmin_token.txt", "w") as f:
        f.write(token)

    print(f"\nLogged in as {api.full_name}.")
    print(f"Token written to garmin_token.txt ({len(token)} characters).")
    print("\nPaste its entire contents into the GitHub secret named GARMIN_TOKEN,")
    print("then delete the file. It stays valid for roughly a year.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
