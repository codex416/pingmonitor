#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json, time, socket, subprocess, threading, requests, os, re
from datetime import datetime

BASE_DIR="/opt/pingmonitor"
CONFIG=os.path.join(BASE_DIR,"config.json")
LOG_DIR=os.path.join(BASE_DIR,"logs")
LOG_FILE=os.path.join(LOG_DIR,"monitor.log")
STATUS_FILE=os.path.join(BASE_DIR,"status.json")
DEFAULT_INTERVAL=60
DEFAULT_PORT=443
DEFAULT_CHECK="ping"
TCP_TIMEOUT=5
PING_TIMEOUT=3

class Monitor:
    def __init__(self):
        self.running_nodes={}
        self.status_lock=threading.Lock()
        os.makedirs(LOG_DIR,exist_ok=True)

    def log(self,msg):
        text=f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(text,flush=True)
        try:
            os.makedirs(LOG_DIR,exist_ok=True)
            with open(LOG_FILE,"a",encoding="utf-8") as f: f.write(text+"\n")
            try: os.chmod(LOG_FILE,0o666)
            except Exception: pass
        except Exception as e: print(f"[Log Error] 写入日志失败: {e}")

    def load_config(self):
        try:
            with open(CONFIG,"r",encoding="utf-8") as f:
                data=json.load(f)
                return data if isinstance(data,dict) else {"nodes":[],"worker":"","interval":DEFAULT_INTERVAL}
        except Exception:
            return {"nodes":[],"worker":"","interval":DEFAULT_INTERVAL}

    def save_status(self,data):
        tmp=STATUS_FILE+".tmp"
        try:
            with open(tmp,"w",encoding="utf-8") as f: json.dump(data,f,indent=4,ensure_ascii=False)
            os.replace(tmp,STATUS_FILE)
            try: os.chmod(STATUS_FILE,0o666)
            except Exception: pass
        except Exception as e: print(f"[Status Save Error] 保存状态失败: {e}")

    def _read_status(self):
        try:
            if not os.path.exists(STATUS_FILE): return {}
            with open(STATUS_FILE,"r",encoding="utf-8") as f:
                d=json.load(f); return d if isinstance(d,dict) else {}
        except Exception: return {}

    def update_status(self,node,result,fail=0):
        with self.status_lock:
            data=self._read_status()
            result["name"]=node["name"]; result["ip"]=node["ip"]; result["fail"]=fail
            result["last"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data[node["ip"]]=result
            self.save_status(data)

    def delete_status(self,ip):
        with self.status_lock:
            data=self._read_status()
            if ip in data:
                del data[ip]; self.save_status(data)

    @staticmethod
    def clean_host(host):
        host=str(host or "").strip()
        return host[1:-1] if host.startswith("[") and host.endswith("]") else host

    def resolve_targets(self,host):
        host=self.clean_host(host)
        out={"ipv4":[],"ipv6":[]}
        try:
            socket.inet_pton(socket.AF_INET,host); out["ipv4"]=[host]; return out
        except OSError: pass
        try:
            socket.inet_pton(socket.AF_INET6,host); out["ipv6"]=[host]; return out
        except OSError: pass
        try:
            infos=socket.getaddrinfo(host,None,socket.AF_UNSPEC,socket.SOCK_STREAM)
        except socket.gaierror:
            return out
        for info in infos:
            fam=info[0]; addr=info[4][0]
            key="ipv6" if fam==socket.AF_INET6 else "ipv4" if fam==socket.AF_INET else None
            if key and addr not in out[key]: out[key].append(addr)
        return out

    @staticmethod
    def parse_ping_delay(output):
        m=re.search(r"time[=<]\s*([0-9]+(?:\.[0-9]+)?)",output or "",re.I)
        return round(float(m.group(1)),2) if m else None

    def ping(self,host):
        host=self.clean_host(host)
        v6=":" in host
        commands=([["ping","-6","-c","1","-W",str(PING_TIMEOUT),host],
                   ["ping6","-c","1","-W",str(PING_TIMEOUT),host]]
                  if v6 else
                  [["ping","-4","-c","1","-W",str(PING_TIMEOUT),host],
                   ["ping","-c","1","-W",str(PING_TIMEOUT),host]])
        for cmd in commands:
            try:
                r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=PING_TIMEOUT+2)
                if r.returncode==0:
                    return {"status":"online","delay":self.parse_ping_delay(r.stdout),"error":""}
            except (FileNotFoundError,subprocess.TimeoutExpired,OSError): pass
        return {"status":"offline","delay":None,"error":"ICMP 不可达"}

    def tcping(self,host,port):
        host=self.clean_host(host); fam=socket.AF_INET6 if ":" in host else socket.AF_INET
        started=time.perf_counter(); s=socket.socket(fam,socket.SOCK_STREAM); s.settimeout(TCP_TIMEOUT)
        try:
            s.connect((host,port,0,0) if fam==socket.AF_INET6 else (host,port))
            return {"status":"online","delay":round((time.perf_counter()-started)*1000,2),"port":port,"error":""}
        except (socket.timeout,ConnectionRefusedError,OSError) as e:
            return {"status":"offline","delay":None,"port":port,"error":str(e)}
        finally: s.close()

    @staticmethod
    def normalize_node(raw):
        check=str(raw.get("check","ping")).strip().lower()
        if check not in {"ping","tcp","both"}: check="ping"
        try: port=int(raw.get("port",DEFAULT_PORT))
        except (TypeError,ValueError): port=DEFAULT_PORT
        return {"name":str(raw.get("name") or raw.get("ip") or "未命名").strip(),
                "ip":str(raw.get("ip") or "").strip(),"check":check,
                "port":max(1,min(65535,port))}

    def check_target(self,address,check,port):
        r={"address":address,"icmp":{"status":"disabled","delay":None},
           "tcp":{"status":"disabled","delay":None,"port":port}}
        if check in {"ping","both"}: r["icmp"]=self.ping(address)
        if check in {"tcp","both"}: r["tcp"]=self.tcping(address,port)
        oks=[]
        if check in {"ping","both"}: oks.append(r["icmp"]["status"]=="online")
        if check in {"tcp","both"}: oks.append(r["tcp"]["status"]=="online")
        r["status"]="online" if any(oks) else "offline"
        if check in {"tcp","both"} and r["tcp"]["status"]=="online":
            r["delay"]=r["tcp"]["delay"]; r["delay_type"]="tcp"
        elif check in {"ping","both"} and r["icmp"]["status"]=="online":
            r["delay"]=r["icmp"]["delay"]; r["delay_type"]="icmp"
        else: r["delay"]=None; r["delay_type"]=""
        return r

    def check_node_once(self,node):
        check,port=node["check"],node["port"]; targets=self.resolve_targets(node["ip"]); families={}
        for family in ("ipv4","ipv6"):
            addrs=targets[family]
            if not addrs:
                families[family]={"available":False,"address":"","status":"unavailable","delay":None,
                    "delay_type":"","icmp":{"status":"unavailable","delay":None},
                    "tcp":{"status":"unavailable","delay":None,"port":port},"addresses":[],"attempts":[]}
                continue
            attempts=[self.check_target(a,check,port) for a in addrs]
            best=next((x for x in attempts if x["status"]=="online"),attempts[0])
            families[family]={"available":True,"address":best["address"],"status":best["status"],
                "delay":best.get("delay"),"delay_type":best.get("delay_type",""),
                "icmp":best.get("icmp"),"tcp":best.get("tcp"),"addresses":addrs,"attempts":attempts}
        available=[families[f] for f in ("ipv4","ipv6") if families[f]["available"]]
        online=[x for x in available if x["status"]=="online"]
        delays=[x["delay"] for x in online if isinstance(x.get("delay"),(int,float))]
        return {"status":"online" if online else "offline",
                "delay":f"{min(delays):.2f}ms" if delays else "-","check":check,"port":port,
                "ipv4":families["ipv4"],"ipv6":families["ipv6"]}

    @staticmethod
    def family_summary(f,check,port):
        if not f.get("available"): return "未发现"
        p=[]; ic=f.get("icmp") or {}; tcp=f.get("tcp") or {}
        if check in {"ping","both"}: p.append(f"ICMP {ic.get('delay','-')}ms" if ic.get("status")=="online" else "ICMP 失败")
        if check in {"tcp","both"}: p.append(f"TCP:{port} {tcp.get('delay','-')}ms" if tcp.get("status")=="online" else f"TCP:{port} 失败")
        return " / ".join(p)

    def notify(self,node,worker,result):
        if not worker: return
        try:
            requests.post(worker,json={"name":node["name"],"ip":node["ip"],"port":node["port"],
                "check":node["check"],"status":"DOWN","time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ipv4":result.get("ipv4"),"ipv6":result.get("ipv6")},timeout=10)
            self.log(f"{node['name']} TG通知成功")
        except Exception as e: self.log(f"TG通知失败: {e}")

    def check_node(self,original):
        original_ip=original["ip"]
        while True:
            cfg=self.load_config()
            raw=next((n for n in cfg.get("nodes",[]) if str(n.get("ip","")).strip()==original_ip),None)
            if not raw:
                self.delete_status(original_ip); self.running_nodes.pop(original_ip,None)
                self.log(f"{original['name']} 已删除或 IP 已修改"); break
            node=self.normalize_node(raw)
            if not node["ip"]: self.running_nodes[original_ip]="stopped"; break
            try: interval=max(5,int(cfg.get("interval",DEFAULT_INTERVAL)))
            except (TypeError,ValueError): interval=DEFAULT_INTERVAL
            worker=str(cfg.get("worker","") or "").strip()
            result=self.check_node_once(node)
            fail=0 if result["status"]=="online" else 1
            self.update_status(node,result,fail)
            self.log(f"{node['name']} [{node['ip']}] {'在线' if result['status']=='online' else '离线'} "
                     f"检测={node['check']} TCP={node['port']} 延迟={result['delay']} "
                     f"IPv4={self.family_summary(result['ipv4'],node['check'],node['port'])} "
                     f"IPv6={self.family_summary(result['ipv6'],node['check'],node['port'])}")
            if result["status"]=="online":
                time.sleep(interval); continue
            recovered=False
            for wait in (3,5):
                time.sleep(wait); retry=self.check_node_once(node)
                if retry["status"]=="online":
                    recovered=True; self.update_status(node,retry,0); self.log(f"{node['name']} 复测恢复 {retry['delay']}"); break
            if recovered:
                time.sleep(interval); continue
            self.log(f"{node['name']} 连续复测失败，确认离线")
            self.update_status(node,result,3); self.notify(node,worker,result)
            self.running_nodes[original_ip]="stopped"; break

    def manager(self):
        while True:
            cfg=self.load_config(); current=set()
            for raw in cfg.get("nodes",[]):
                node=self.normalize_node(raw); ip=node["ip"]
                if not ip: continue
                current.add(ip)
                if ip not in self.running_nodes:
                    self.running_nodes[ip]="running"
                    threading.Thread(target=self.check_node,args=(node,),daemon=True).start()
                    self.log(f"启动监控: {node['name']} [检测={node['check']}, TCP端口={node['port']}]")
            time.sleep(10)

    def start(self):
        self.log("PingMonitor启动"); self.manager()

if __name__=="__main__": Monitor().start()
