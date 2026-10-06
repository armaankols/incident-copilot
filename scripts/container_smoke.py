"""Build-independent offline checks for a locally built Docker image.

Creates an isolated named volume and container, checks HTTP and ledger/replay
persistence across restart, then removes only those test resources.
"""
import argparse
from datetime import datetime, timezone
import json
from http.client import HTTPException
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def check(image):
    name = "copilot-smoke-"+uuid.uuid4().hex[:8]
    volume = name+"-data"
    created = False
    try:
        docker("volume", "create", volume)
        docker("run", "-d", "--name", name, "-p", "127.0.0.1::8080", "-v", f"{volume}:/data", image)
        created = True
        mapping = docker("port", name, "8080/tcp").splitlines()[0]
        base = "http://"+mapping
        def request(path):
            with urllib.request.urlopen(base+path, timeout=5) as response:
                return response.status, response.read()
        for _ in range(60):
            try:
                status, body = request("/healthz")
                assert status == 200 and json.loads(body)["status"] == "ok"
                break
            except (urllib.error.URLError, TimeoutError, HTTPException, ConnectionResetError):
                time.sleep(.5)
        else:
            raise RuntimeError("Container did not become healthy")
        statuses = {path: request(path)[0] for path in ("/healthz", "/", "/static/demo.js", "/api/config", "/api/replay")}
        assert all(status == 200 for status in statuses.values())
        req = urllib.request.Request(base+"/api/runs", data=b'{}', headers={"Content-Type":"application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("Live endpoint must reject missing credentials")
        except urllib.error.HTTPError as error:
            assert error.code == 503
        uid_line = docker("exec", name, "sh", "-c", "sed -n '/^Uid:/p' /proc/1/status")
        assert uid_line.split()[1:] == ["10001"]*4
        seed = "from copilot.budget import Ledger; import os; l=Ledger(os.environ['BUDGET_DB']); r=l.reserve(.25,2,'smoke'); l.settle(r,.1); l.save_replay('persistent-check','{\"offline\":true}'); print(l.spent())"
        assert docker("exec", "--user", "10001", name, "python", "-c", seed) == "0.1"
        # Simulate a provisioned volume whose mount root is owned by root.
        docker("exec", "--user", "root", name, "chown", "root:root", "/data")
        docker("restart", name)
        base = "http://" + docker("port", name, "8080/tcp").splitlines()[0]
        for _ in range(60):
            try:
                request("/healthz")
                break
            except (urllib.error.URLError, TimeoutError, HTTPException, ConnectionResetError):
                time.sleep(.5)
        else:
            raise RuntimeError("Container did not become healthy after restart")
        cfg = json.loads(request("/api/config")[1])
        assert cfg["spent_today_usd"] == .1
        verify = "from copilot.budget import Ledger; import os; l=Ledger(os.environ['BUDGET_DB']); assert l.replay('persistent-check')=='{\"offline\":true}'; print('persistence verified')"
        assert docker("exec", "--user", "10001", name, "python", "-c", verify) == "persistence verified"
        result = {"measured_at": datetime.now(timezone.utc).isoformat(), "image": image, "image_id": docker("image", "inspect", image, "--format", "{{.Id}}"),
                  "platform": docker("image", "inspect", image, "--format", "{{.Os}}/{{.Architecture}}"), "http_statuses": statuses, "no_key_status": 503,
                  "persistent_test_charge_usd": cfg["spent_today_usd"], "replay_survived_restart": True, "server_uid": 10001, "root_owned_mount_repaired": True}
        print(json.dumps(result, indent=2))
        return result
    except BaseException:
        if created:
            print(docker("logs", name))
        raise
    finally:
        if created:
            docker("rm", "-f", name)
        docker("volume", "rm", volume)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="incident-copilot:local")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.image)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+"\n")
