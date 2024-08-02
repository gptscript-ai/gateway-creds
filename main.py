import datetime
import json
import os
import subprocess
import sys
from time import sleep
from uuid import uuid4

import pytz
import requests
from gptscript.gptscript import GPTScript
from gptscript.opts import Options


async def main():
    gateway_url = os.environ.get("GPTSCRIPT_GATEWAY_URL", "https://gateway-api.gptscript.ai")

    token, expiration = "", ""
    if "GPTSCRIPT_EXISTING_CREDENTIAL" in os.environ:
        # If the existing credential is set, then try to refresh it.
        token, expiration = refresh_token(gateway_url, os.environ["GPTSCRIPT_EXISTING_CREDENTIAL"])

    if token == "":
        # If there's no existing credential or refresh failed, then create a new one.
        token, expiration = await create_token(
            gateway_url,
            os.environ.get("GPTSCRIPT_GATEWAY_AUTH_SERVICE_NAME", ""),
        )

    print('{"env": {"GPTSCRIPT_GATEWAY_API_KEY": "%s"}, "expiresAt": "%s", "refreshToken": "%s"}' % (
        token, expiration, token,
    ))


async def create_token(gateway_url: str, service_name: str) -> (str, str):
    token_request_id = str(uuid4())

    resp = requests.post(f"{gateway_url}/api/token-request", json={"id": token_request_id, "serviceName": service_name})
    if resp.status_code != 200:
        print(resp.text)
        sys.exit(1)

    token_path = resp.json()["token-path"]
    gptscript = GPTScript()
    try:
        run = gptscript.run(
            "sys.prompt",
            Options(input=json.dumps(
                {
                    "message": f"Opening browser to {token_path}. " +
                               "If there is an issue paste this link into a browser manually."
                }
            ))
        )
        await run.text()
        subprocess.run([sys.executable, "-m", "webbrowser", "-n", token_path], stdout=subprocess.DEVNULL)
    except:
        pass
    finally:
        gptscript.close()

    token_resp = poll_for_token(gateway_url, token_request_id)

    return token_resp["token"], calculate_expires_at(token_resp.get("expiresAt", ""))


def refresh_token(gateway_url: str, cred: str) -> (str, str):
    if cred == "":
        return "", ""

    try:
        token = json.loads(cred)["refreshToken"]
    except json.decoder.JSONDecodeError:
        return "", ""

    resp = requests.post(f"{gateway_url}/api/tokens", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return "", ""

    res = resp.json()
    return res["token"], calculate_expires_at(res.get("expiresAt", ""))


def calculate_expires_at(expires_at: str) -> str:
    expiration = datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(hours=1)
    if expires_at != "":
        expiration = datetime.datetime.fromisoformat(expires_at)
        now = datetime.datetime.now(tz=expiration.tzinfo)
        # Tokens expire in half the time as the actual expiration, so they can be refreshed.
        expiration = now + (expiration - now) / 2

    return expiration.isoformat()


def create_token_request(gateway_url: str, id: str):
    resp = requests.post(f"{gateway_url}/api/token-request", json={"id": id})
    if resp.status_code != 200:
        print(resp.text)
        sys.exit(1)


def poll_for_token(gateway_url: str, id: str) -> dict:
    while True:
        resp = requests.get(f"{gateway_url}/api/token-request/{id}")
        if resp.status_code == 200:
            res = resp.json()
            if "token" in res and res["token"] is not None and res["token"] != "":
                return res

            sleep(1)
        else:
            print(resp.text)
            sys.exit(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
    try:
        pass
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("User cancelled")
        exit(1)
