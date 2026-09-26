"""把一个 workbuddy2api 部署目录下的 WorkBuddy 凭证导入 cli2api。

- 字段映射: account.uid -> uid, auth.accessToken -> access_token, auth.refreshToken -> refresh_token,
  auth.expiresAt -> expires_at, auth.domain -> domain, account.nickname -> nickname,
  account.enterpriseId -> enterprise_id
- 格式: workbuddy-oauth-v1（cli2api 的 import format）
- 令牌值只在内存中流转，不打印、不落盘（除 cli2api 自己的数据库）

用法:
  python import-wb2api-auths.py --auth-dir <目录>                    # 预览（不提交）
  python import-wb2api-auths.py --auth-dir <目录> --apply            # 导入（默认 enabled=false）
  python import-wb2api-auths.py --auth-dir <目录> --apply --enable   # 导入并启用

<目录> 是存放 workbuddy-*.json 的 auths 目录，例如某个 workbuddy2api 部署的 auths/。
路径不写死，避免把本机目录结构带进版本库。
"""
import glob
import json
import os
import subprocess
import sys

BASE = "http://127.0.0.1:3010"
HERE = os.path.dirname(os.path.abspath(__file__))

apply = "--apply" in sys.argv
enable = "--enable" in sys.argv

auth_dir = ""
if "--auth-dir" in sys.argv:
    i = sys.argv.index("--auth-dir")
    if i + 1 < len(sys.argv):
        auth_dir = sys.argv[i + 1]
if not auth_dir:
    sys.exit("必须用 --auth-dir <目录> 指定存放 workbuddy-*.json 的目录")

AUTH_GLOB = os.path.join(auth_dir, "workbuddy-*.json")

key = subprocess.run([sys.executable, os.path.join(HERE, "get-key.py")],
                     capture_output=True, text=True).stdout.strip()
if not key:
    sys.exit("无法读取管理员密钥（get-key.py 失败）")


def convert(path):
    d = json.load(open(path, encoding="utf-8"))
    acc, auth = d.get("account") or {}, d.get("auth") or {}
    cred = {
        "uid": acc.get("uid") or "",
        "access_token": auth.get("accessToken") or "",
        "refresh_token": auth.get("refreshToken") or "",
        "expires_at": int(auth.get("expiresAt") or 0),
        "domain": auth.get("domain") or "",
        "enterprise_id": acc.get("enterpriseId") or "",
        "nickname": acc.get("nickname") or "",
    }
    org = acc.get("uid") or os.path.basename(path)
    name = "workbuddy-" + (acc.get("nickname") or org)[:24]
    payload = {
        "format": "workbuddy-oauth-v1",
        "name": name,
        "provider": "workbuddy",
        "region": "global" if "codebuddy.cn" not in cred["domain"] else "cn",
        "enabled": enable,
        "max_inflight": 1,
        "priority": 10,
        "credential": cred,
    }
    return name, payload


for f in sorted(glob.glob(AUTH_GLOB)):
    name, payload = convert(f)
    cred = payload["credential"]
    print("文件:", os.path.basename(f))
    print("  导入名:", name, "| region:", payload["region"], "| enabled:", payload["enabled"])
    print("  uid=%s domain=%s expires_at=%s 企业id=%s" % (
        cred["uid"], cred["domain"], cred["expires_at"], cred["enterprise_id"] or "(空)"))
    print("  access_token: %d 字符 | refresh_token: %d 字符" % (
        len(cred["access_token"]), len(cred["refresh_token"])))
    if not apply:
        print("  [预览模式] 未提交\n")
        continue
    body = json.dumps(payload, ensure_ascii=False)
    r = subprocess.run(["curl", "-s", "-m", "60", "-X", "POST",
                        BASE + "/api/accounts/import",
                        "-H", "Authorization: Bearer " + key,
                        "-H", "Content-Type: application/json",
                        "--data-binary", "@-"],
                       input=body.encode("utf-8"), capture_output=True)
    out = r.stdout.decode("utf-8", "replace")
    try:
        j = json.loads(out)
        if j.get("id"):
            print("  → 导入成功 id=%s status=%s enabled=%s\n" % (
                j.get("id"), j.get("status"), j.get("enabled")))
        else:
            print("  → 失败:", json.dumps(j, ensure_ascii=False)[:300], "\n")
    except Exception:
        print("  → 原始响应:", out[:300], "\n")
