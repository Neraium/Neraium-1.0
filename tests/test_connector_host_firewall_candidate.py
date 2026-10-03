"""Execute bootstrap firewall logic with fake tools; never alter host networking."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

# Minimal command simulator preserves chain semantics and catches flushing an
# attached chain. Tests execute the real script, not reconstructed shell rules.
FAKE_TOOL = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
if Path(sys.argv[0]).name == "getent":
    print(("93.184.216.34" if sys.argv[-1].startswith("bfzcudq5o2") else "3.5.6.7") + " STREAM mock")
    raise SystemExit(0)
p = Path(os.environ["FIREWALL_TEST_STATE"])
state = json.loads(p.read_text())
table = state["v6" if Path(sys.argv[0]).name == "ip6tables" else "v4"]
op, chain, *rule = sys.argv[1:]
if op == "-N":
    if chain in table: raise SystemExit(1)
    table[chain] = []
elif op == "-F":
    if any(r[-2:] == ["-j", chain] for r in table["OUTPUT"]):
        raise RuntimeError("flushed attached chain")
    if chain not in table: raise SystemExit(1)
    table[chain] = []
elif op == "-X":
    if chain not in table: raise SystemExit(1)
    del table[chain]
elif op == "-C":
    raise SystemExit(0 if rule in table.get(chain, []) else 1)
elif op == "-D":
    if rule not in table.get(chain, []): raise SystemExit(1)
    table[chain].remove(rule)
elif op == "-A": table[chain].append(rule)
elif op == "-I": table[chain].insert(int(rule[0])-1,rule[1:])
else: raise RuntimeError("unexpected command")
p.write_text(json.dumps(state))
'''


def permits(table, uid, destination, port, protocol="tcp"):
    def run(chain):
        for rule in table[chain]:
            if "--uid-owner" in rule and rule[rule.index("--uid-owner")+1] != str(uid): continue
            if "--ctstate" in rule: continue  # Test new connections only.
            if "-d" in rule and ipaddress.ip_address(destination) not in ipaddress.ip_network(rule[rule.index("-d")+1]): continue
            if "-p" in rule and rule[rule.index("-p")+1] != protocol: continue
            if "--dport" in rule and int(rule[rule.index("--dport")+1]) != port: continue
            target=rule[rule.index("-j")+1]
            if target=="ACCEPT": return True
            if target=="REJECT": return False
            result=run(target)
            if result is not None: return result
        return None
    return run("OUTPUT")


def test_refresh_preserves_unrelated_hooks_and_restricts_child_and_root(tmp_path):
    state=tmp_path/"state.json"
    hook=lambda uid,chain:["-m","owner","--uid-owner",str(uid),"-j",chain]
    state.write_text(json.dumps({
        "v4":{"OUTPUT":[hook(999,"UNRELATED"),hook(0,"NERAIUM_BROKER_A"),hook(10002,"NERAIUM_CONNECTOR_A")],
              "UNRELATED":[["-j","REJECT"]],"NERAIUM_BROKER_A":[["-j","REJECT"]],"NERAIUM_CONNECTOR_A":[["-j","REJECT"]]},
        "v6":{"OUTPUT":[hook(10002,"NERAIUM_CONNECTOR"),hook(0,"NERAIUM_BROKER")],
              "NERAIUM_CONNECTOR":[["-j","REJECT"]],"NERAIUM_BROKER":[["-j","REJECT"]]}}))
    bin_dir=tmp_path/"bin";bin_dir.mkdir()
    for name in ("iptables","ip6tables","getent"):
        path=bin_dir/name;path.write_text(FAKE_TOOL);path.chmod(0o755)
    source=(ROOT/"infra/production/connector-executor-user-data.sh").read_text()
    script=tmp_path/"firewall.sh"
    script.write_text(source.split("<<'FIREWALL'\n",1)[1].split("\nFIREWALL",1)[0])
    env={**os.environ,"PATH":str(bin_dir)+":/usr/bin:/bin","FIREWALL_TEST_STATE":str(state)}
    for _ in range(2):
        subprocess.run(["bash",str(script)],env=env,check=True,capture_output=True)
        rules=json.loads(state.read_text())
        assert hook(999,"UNRELATED") in rules["v4"]["OUTPUT"]
        for uid in (0,10002):
            assert permits(rules["v4"],uid,"8.8.8.8",443) is False
            assert permits(rules["v4"],uid,"10.40.1.1",5432) is False
            assert permits(rules["v4"],uid,"93.184.216.34",502) is False
            assert permits(rules["v6"],uid,"::1",443) is False
        assert permits(rules["v4"],10002,"93.184.216.34",443) is True
        assert permits(rules["v4"],10002,"169.254.169.254",80) is False
        assert permits(rules["v4"],10002,"3.5.6.7",443) is False
        assert permits(rules["v4"],0,"3.5.6.7",443) is True
        assert permits(rules["v4"],0,"169.254.169.254",80) is True
        assert permits(rules["v4"],0,"93.184.216.34",443) is False
