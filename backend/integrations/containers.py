"""
컨테이너 설정 점검. `docker inspect` 결과(설정)만 본다. 런타임 동작은 보지 않는다.

이 모듈이 존재하는 이유:
  1) 상시 기동 중인 `privileged=true` 빌더 컨테이너가 호스트 점검에서 발견되었다.
     privileged 컨테이너는 호스트 커널/장치에 그대로 접근하므로 사실상 root 셸과 같다.
  2) Docker 는 포트를 공개할 때 자기 iptables 규칙(DOCKER 체인)을 직접 삽입한다.
     이 규칙은 ufw 보다 앞서 평가되므로 `ufw deny incoming` 이 걸려 있어도
     0.0.0.0 으로 공개된 컨테이너 포트는 외부에서 그대로 접속된다. ufw 는 방어선이 아니다.

조용히 실패하지 않는다. docker 를 못 쓰면 available=False 와 함께 한국어 사유 + 조치 명령을 반환한다.
`docker inspect` 출력 형태는 버전마다 다르므로 모든 접근은 .get() 사슬로 방어한다.
"""
import json
import logging
import shutil
import subprocess

logger = logging.getLogger("containers")

# 호스트 root 와 동등한 권한을 주는 소켓 경로
DOCKER_SOCKETS = ("/var/run/docker.sock", "/run/docker.sock")

# 컨테이너 탈출/호스트 조작에 직접 쓰이는 케이퍼빌리티
DANGEROUS_CAPS = ("SYS_ADMIN", "SYS_PTRACE", "SYS_MODULE", "NET_ADMIN", "DAC_READ_SEARCH")

# 모든 인터페이스로 공개된 것으로 간주하는 HostIp 값
WILDCARD_IPS = ("", "0.0.0.0", "::")

_SEVERITY_RANK = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}


# --------------------------------------------------------------------------
# 파싱 보조 (모두 순수 함수. 어떤 입력에도 예외를 던지지 않는다)
# --------------------------------------------------------------------------
def _d(obj, key: str) -> dict:
    """obj[key] 를 dict 로 꺼낸다. 없거나 타입이 다르면 빈 dict."""
    if not isinstance(obj, dict):
        return {}
    v = obj.get(key)
    return v if isinstance(v, dict) else {}


def _l(obj, key: str) -> list:
    """obj[key] 를 list 로 꺼낸다. 없거나 타입이 다르면 빈 list."""
    if not isinstance(obj, dict):
        return []
    v = obj.get(key)
    return v if isinstance(v, list) else []


def _finding(code: str, severity: str, title_ko: str, detail_ko: str, fix_ko: str) -> dict:
    return {"code": code, "severity": severity, "title_ko": title_ko, "detail_ko": detail_ko, "fix_ko": fix_ko}


def _container_name(obj: dict) -> str:
    """`/builder` 처럼 앞에 슬래시가 붙어 나온다. 없으면 짧은 ID 로 대체."""
    name = obj.get("Name") if isinstance(obj, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip().lstrip("/")
    return _short_id(obj) or "(이름없음)"


def _short_id(obj: dict) -> str:
    cid = obj.get("Id") if isinstance(obj, dict) else None
    if not isinstance(cid, str):
        cid = ""
    return cid[:12]


def _image_of(obj: dict) -> str:
    img = _d(obj, "Config").get("Image")
    if isinstance(img, str) and img:
        return img
    img = obj.get("Image") if isinstance(obj, dict) else None
    return img if isinstance(img, str) else ""


def _restart_of(obj: dict) -> str:
    """RestartPolicy.Name. 'always'/'unless-stopped' 는 상시 기동을 뜻한다."""
    name = _d(_d(obj, "HostConfig"), "RestartPolicy").get("Name")
    return name if isinstance(name, str) else ""


def _network_mode(obj: dict) -> str:
    mode = _d(obj, "HostConfig").get("NetworkMode")
    return mode if isinstance(mode, str) else ""


def _bind_sources(obj: dict) -> list[str]:
    """호스트에서 마운트된 경로 목록. Mounts(Source) 와 HostConfig.Binds 둘 다 본다."""
    sources: list[str] = []
    for m in _l(obj, "Mounts"):
        if not isinstance(m, dict):
            continue
        src = m.get("Source")
        if isinstance(src, str) and src:
            sources.append(src)
    for b in _l(_d(obj, "HostConfig"), "Binds"):
        # "host_path:container_path:ro" 형식. 첫 필드가 호스트 경로.
        if isinstance(b, str) and b:
            sources.append(b.split(":", 1)[0])
    return sources


def _published_ports(obj: dict) -> list[str]:
    """모든 인터페이스로 공개된 포트를 사람이 읽는 문자열로 돌려준다. 예: '0.0.0.0:8080 -> 8080/tcp'"""
    found: list[str] = []
    seen: set[str] = set()
    sources = (
        _d(_d(obj, "NetworkSettings"), "Ports"),
        _d(_d(obj, "HostConfig"), "PortBindings"),
    )
    for mapping in sources:
        for spec, bindings in mapping.items():
            if not isinstance(bindings, list):
                continue  # 공개되지 않은 포트는 null 로 나온다
            for b in bindings:
                if not isinstance(b, dict):
                    continue
                host_ip = b.get("HostIp")
                host_ip = host_ip if isinstance(host_ip, str) else ""
                if host_ip not in WILDCARD_IPS:
                    continue
                host_port = b.get("HostPort")
                host_port = host_port if isinstance(host_port, str) else ""
                label = f"{host_ip or '0.0.0.0'}:{host_port or '?'} -> {spec}"
                if label not in seen:
                    seen.add(label)
                    found.append(label)
    return found


def _first_port_number(labels: list[str]) -> str:
    """조치 명령 예시에 쓸 대표 포트 번호 하나."""
    for label in labels:
        head = label.split(" -> ", 1)[0]
        port = head.rsplit(":", 1)[-1]
        if port.isdigit():
            return port
    return "PORT"


# --------------------------------------------------------------------------
# 점검
# --------------------------------------------------------------------------
def audit_container(obj: dict) -> dict:
    """`docker inspect` 결과 1개 → 점검 결과."""
    if not isinstance(obj, dict):
        obj = {}
    name = _container_name(obj)
    host = _d(obj, "HostConfig")
    findings: list[dict] = []

    # --- privileged: 호스트 root 와 동등 ---
    privileged = bool(host.get("Privileged"))
    if privileged:
        findings.append(_finding(
            "privileged", "CRITICAL",
            "특권 컨테이너 (privileged=true)",
            f"'{name}' 이 --privileged 로 실행 중입니다. 호스트의 모든 장치(/dev)와 커널 기능에 제한 없이 "
            "접근할 수 있어, 이 컨테이너를 장악하면 호스트 root 를 장악한 것과 같습니다. "
            f"재시작 정책이 '{_restart_of(obj) or 'no'}' 이므로 상시 떠 있다면 노출 시간이 계속 유지됩니다.",
            f"상시 기동을 멈추고 필요할 때만 올리세요: `docker update --restart=no {name}` 후 `docker stop {name}`. "
            f"buildx 빌더라면 `docker buildx stop {name}` 로 내리고 빌드할 때만 기동하세요. "
            "계속 필요하다면 --privileged 대신 필요한 것만 주세요: `--cap-add=<필요한_CAP> --device=<필요한_장치>`.",
        ))

    # --- docker.sock 마운트: privileged 와 동급 ---
    socks = [s for s in _bind_sources(obj) if s in DOCKER_SOCKETS]
    if socks:
        socks_txt = ", ".join(sorted(set(socks)))
        findings.append(_finding(
            "docker_sock", "CRITICAL",
            "docker 소켓이 컨테이너 안에 마운트됨",
            f"'{name}' 안에 {socks_txt} 가 마운트되어 있습니다. 이 소켓에 쓸 수 있다는 것은 "
            "호스트 root 권한을 가진 것과 같습니다 (소켓으로 `-v /:/host --privileged` 컨테이너를 새로 만들면 "
            "호스트 파일시스템 전체를 그대로 읽고 쓸 수 있습니다). 컨테이너 격리는 이 경우 의미가 없습니다.",
            f"마운트를 제거하세요: `docker stop {name} && docker rm {name}` 후 `-v {socks[0]}:{socks[0]}` 없이 다시 기동. "
            "컨테이너가 docker API 를 꼭 써야 한다면 소켓을 직접 주지 말고 읽기 전용 프록시(tecnativa/docker-socket-proxy 등)를 "
            "앞에 두고 필요한 엔드포인트만 허용하세요.",
        ))

    # --- host 네트워크: 네트워크 격리 없음 ---
    netmode = _network_mode(obj)
    if netmode == "host":
        findings.append(_finding(
            "host_network", "WARNING",
            "호스트 네트워크 사용 (network=host)",
            f"'{name}' 이 --network=host 로 실행 중입니다. 컨테이너가 여는 모든 포트가 호스트의 포트로 "
            "그대로 열리며, 컨테이너 안에서 호스트의 루프백(127.0.0.1)에 붙은 서비스에도 접근할 수 있습니다. "
            "네트워크 격리가 전혀 없습니다.",
            f"`docker stop {name} && docker rm {name}` 후 --network=host 를 빼고 필요한 포트만 "
            f"`-p 127.0.0.1:PORT:PORT` 로 공개해 다시 기동하세요. "
            "지금 열려 있는 포트는 `sudo ss -tulpn` 으로 확인할 수 있습니다.",
        ))
    else:
        # host 네트워크면 이미 위에서 다뤘으므로 포트 공개는 중복 보고하지 않는다
        ports = _published_ports(obj)
        if ports:
            ports_txt = ", ".join(ports)
            sample = _first_port_number(ports)
            findings.append(_finding(
                "port_all_interfaces", "WARNING",
                "포트가 모든 인터페이스로 공개됨",
                f"'{name}' 의 포트 {ports_txt} 가 모든 인터페이스에 공개되어 외부에서 직접 접속됩니다. "
                "Docker 는 포트를 공개할 때 iptables 의 DOCKER 체인에 자기 규칙을 직접 넣고, 이 규칙은 "
                "ufw 규칙보다 먼저 평가됩니다. 따라서 `ufw deny incoming` 이 걸려 있어도 이 포트는 막히지 않습니다. "
                "ufw status 가 깨끗하다고 안전하다고 판단하면 안 됩니다.",
                f"`docker stop {name} && docker rm {name}` 후 루프백에만 묶어 다시 기동하세요: "
                f"`-p 127.0.0.1:{sample}:{sample}`. 외부 공개가 필요하면 리버스 프록시(nginx)를 앞에 두고 "
                f"컨테이너는 루프백에만 두세요. 외부 노출 여부는 `sudo ss -tulpn | grep :{sample}` 와 "
                f"`sudo iptables -L DOCKER -n` 으로 확인하세요.",
            ))

    # --- host PID: 호스트 프로세스가 그대로 보인다 ---
    if _d(obj, "HostConfig").get("PidMode") == "host":
        findings.append(_finding(
            "host_pid", "WARNING",
            "호스트 PID 네임스페이스 사용 (pid=host)",
            f"'{name}' 이 --pid=host 로 실행 중입니다. 호스트의 모든 프로세스가 컨테이너 안에서 그대로 보이며, "
            "명령줄 인자에 실린 비밀값(/proc/<pid>/cmdline)을 읽거나 권한이 맞으면 호스트 프로세스에 시그널을 보낼 수 있습니다.",
            f"`docker stop {name} && docker rm {name}` 후 --pid=host 를 빼고 다시 기동하세요. "
            "호스트 프로세스 모니터링이 목적이라면 컨테이너 대신 호스트에서 직접 수집하는 편이 안전합니다.",
        ))

    # --- 위험 케이퍼빌리티 추가 ---
    cap_add = [str(c).upper() for c in _l(host, "CapAdd") if isinstance(c, (str, bytes))]
    risky = [c for c in DANGEROUS_CAPS if c in cap_add]
    if risky:
        risky_txt = ", ".join(risky)
        findings.append(_finding(
            "cap_add", "WARNING",
            f"위험한 케이퍼빌리티 추가: {risky_txt}",
            f"'{name}' 에 {risky_txt} 가 추가되어 있습니다. SYS_ADMIN 은 사실상 privileged 에 가깝고, "
            "SYS_MODULE 은 호스트 커널 모듈 적재를, SYS_PTRACE 는 다른 프로세스 메모리 열람을, "
            "DAC_READ_SEARCH 는 파일 권한 우회를, NET_ADMIN 은 호스트 네트워크 설정 변경을 허용합니다.",
            f"`docker inspect -f '{{{{.HostConfig.CapAdd}}}}' {name}` 로 현재 값을 확인하고, "
            f"`docker stop {name} && docker rm {name}` 후 `--cap-add` 를 빼고 다시 기동하세요. "
            "정말 필요한 한 가지만 남기고 `--cap-drop=ALL` 을 함께 주는 것이 기본입니다.",
        ))

    # --- root 로 실행 (INFO: 매우 흔하므로 경보로 올리지 않는다) ---
    user = _d(obj, "Config").get("User")
    user = user.strip() if isinstance(user, str) else ""
    if user in ("", "0", "root"):
        findings.append(_finding(
            "run_as_root", "INFO",
            "컨테이너가 root 로 실행됨",
            f"'{name}' 의 Config.User 가 비어 있거나 root 입니다. 컨테이너 안에서 root 로 동작합니다. "
            "매우 흔한 기본값이며 그 자체로 침해는 아니지만, 다른 취약점과 겹치면 피해 범위를 키웁니다.",
            f"이미지에 비특권 사용자를 만들고(Dockerfile 의 `USER 10001`) 기동 시 `--user 10001:10001` 을 주세요. "
            "함께 `--read-only` 와 `--security-opt=no-new-privileges` 를 붙이면 더 좋습니다.",
        ))

    return {
        "id": _short_id(obj),
        "name": name,
        "image": _image_of(obj),
        "privileged": privileged,
        "restart": _restart_of(obj),
        "findings": findings,
    }


def _sort_key(row: dict):
    """findings 있는 것 우선, 그 다음 심각도 높은 순, 마지막으로 이름 순."""
    findings = row.get("findings") or []
    worst = max((_SEVERITY_RANK.get(f.get("severity", ""), 0) for f in findings), default=0)
    return (0 if findings else 1, -worst, -len(findings), row.get("name", ""))


def actionable(row: dict) -> list[dict]:
    """INFO 를 뺀, 실제로 조치가 필요한 findings. 알림과 대시보드 카운트는 이것만 본다."""
    return [f for f in (row.get("findings") or []) if f.get("severity") in ("CRITICAL", "WARNING")]


def audit_all(objs: list[dict]) -> list[dict]:
    """`docker inspect` 결과 여러 개 → 점검 결과 목록. findings 있는 컨테이너를 앞에 둔다."""
    if not isinstance(objs, list):
        return []
    rows = [audit_container(o) for o in objs]
    rows.sort(key=_sort_key)
    return rows


# --------------------------------------------------------------------------
# docker 실행
# --------------------------------------------------------------------------
class DockerClient:
    """docker CLI 호출기. 실패를 삼키지 않고 사유와 조치를 한국어로 돌려준다."""

    def __init__(self, docker_bin: str = "docker", use_sudo: bool | None = None):
        self.docker_bin = docker_bin or "docker"
        # docker 그룹 소속이 일반적인 구성이므로 기본은 sudo 없이 호출한다
        self.use_sudo = False if use_sudo is None else bool(use_sudo)
        self._last_error = ""

    # --- 저수준 실행 ---
    def _cmd(self, *args: str) -> list[str]:
        base = [self.docker_bin, *args]
        if self.use_sudo:
            return ["sudo", "-n", *base]
        return base

    def _run(self, *args: str, timeout: int = 15) -> tuple[int, str]:
        rc, out = self._run_once(*args, timeout=timeout)
        # 소켓 권한이 없으면 한 번만 sudo -n 으로 재시도한다. 개발 환경(docker 그룹 소속)에서는
        # sudo 없이 바로 되고, 운영 서비스 계정에서는 deploy/sudoers-secdash 의 읽기 전용 허용으로 넘어간다.
        # 서비스 계정을 docker 그룹에 넣는 것은 root 를 주는 것과 같으므로 그 길은 쓰지 않는다.
        if rc != 0 and not self.use_sudo and "permission denied" in self._last_error.lower():
            self.use_sudo = True
            rc, out = self._run_once(*args, timeout=timeout)
            if rc != 0:
                self.use_sudo = False   # sudo 도 안 되면 원래대로 되돌려 다음 판정을 흐리지 않는다
        return rc, out

    def _run_once(self, *args: str, timeout: int = 15) -> tuple[int, str]:
        if not shutil.which(self.docker_bin):
            self._last_error = "docker 실행 파일을 찾을 수 없음"
            return 127, ""
        try:
            proc = subprocess.run(
                self._cmd(*args), capture_output=True, text=True, timeout=timeout,
                env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
            )
        except FileNotFoundError as e:
            self._last_error = str(e)
            return 127, ""
        except subprocess.TimeoutExpired:
            self._last_error = "docker 응답 시간 초과 (데몬이 멈춰 있을 수 있음)"
            return 124, ""
        except OSError as e:
            self._last_error = str(e)
            return 1, ""
        out = (proc.stdout or "")
        err = (proc.stderr or "")
        if proc.returncode != 0:
            combined = (err + out).strip()
            self._last_error = combined.splitlines()[-1] if combined else f"rc={proc.returncode}"
        return proc.returncode, out

    # --- 상태 ---
    def availability(self) -> tuple[bool, str, str]:
        """(사용 가능 여부, 사유, 해결 힌트)"""
        if not shutil.which(self.docker_bin):
            return (False, "docker 미설치",
                    "컨테이너를 쓰지 않는 호스트라면 무시해도 됩니다. 쓸 예정이라면 "
                    "`sudo apt install docker.io` 또는 공식 저장소로 docker-ce 를 설치하세요.")
        rc, _ = self._run("version", "--format", "{{.Server.Version}}", timeout=10)
        if rc == 0:
            return True, "", ""
        err = self._last_error
        low = err.lower()
        if "permission denied" in low:
            return (False, f"docker 소켓 접근 권한 없음 ({err[:120]})",
                    "서비스 계정을 docker 그룹에 넣지 마세요. docker 그룹은 호스트 root 와 동등한 권한입니다. "
                    "대신 deploy/sudoers-secdash 에 `secdash ALL=(root) NOPASSWD: /usr/bin/docker ps -q, "
                    "/usr/bin/docker inspect *` 처럼 읽기 명령만 한정 허용하고 DockerClient(use_sudo=True) 로 호출하세요.")
        if "cannot connect to the docker daemon" in low or "is the docker daemon running" in low:
            return (False, "docker 데몬이 실행 중이 아님",
                    "`sudo systemctl status docker` 로 확인하고, 필요하면 `sudo systemctl enable --now docker` 로 기동하세요. "
                    "의도적으로 내려둔 것이라면 이 항목은 무시해도 됩니다.")
        if "sudo:" in low or "password is required" in low:
            return (False, f"sudo 로 docker 를 호출할 수 없음 ({err[:120]})",
                    "deploy/sudoers-secdash 설치 여부를 확인하세요. NOPASSWD 로 docker ps / docker inspect 만 허용하면 됩니다.")
        if "timeout" in low or "시간 초과" in err:
            return (False, "docker 응답 시간 초과",
                    "`sudo systemctl status docker` 와 `journalctl -u docker -n 50` 으로 데몬 상태를 확인하세요.")
        return (False, f"docker 오류: {err[:200]}",
                "`docker version` 을 서비스 계정으로 직접 실행해 같은 오류가 재현되는지 확인하세요.")

    # --- 조회 ---
    def inspect_running(self) -> list[dict] | None:
        """실행 중인 컨테이너의 `docker inspect` 결과. 실패 시 None, 컨테이너가 없으면 []."""
        rc, out = self._run("ps", "-q", timeout=15)
        if rc != 0:
            logger.warning(f"docker ps 실패: {self._last_error}")
            return None
        ids = [line.strip() for line in out.splitlines() if line.strip()]
        if not ids:
            return []   # 컨테이너가 없는 것은 실패가 아니다
        rc, out = self._run("inspect", *ids, timeout=30)
        if rc != 0:
            logger.warning(f"docker inspect 실패: {self._last_error}")
            return None
        try:
            data = json.loads(out)
        except (ValueError, TypeError) as e:
            self._last_error = f"docker inspect 출력 파싱 실패: {e}"
            logger.warning(self._last_error)
            return None
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            self._last_error = "docker inspect 출력이 예상한 JSON 배열이 아님"
            return None
        return [o for o in data if isinstance(o, dict)]

    def snapshot(self) -> dict:
        """대시보드용 요약. JSON 직렬화 가능한 dict 만 돌려준다."""
        ok, reason, fix_hint = self.availability()
        if not ok:
            return {
                "available": False, "reason": reason, "fix_hint": fix_hint,
                "containers": [],
                "counts": {"total": 0, "privileged": 0, "with_findings": 0},
            }
        objs = self.inspect_running()
        if objs is None:
            return {
                "available": False,
                "reason": f"컨테이너 목록을 읽지 못함: {self._last_error or '알 수 없는 오류'}",
                "fix_hint": "서비스 계정으로 `docker ps -q` 와 `docker inspect <ID>` 를 직접 실행해 오류를 확인하세요.",
                "containers": [],
                "counts": {"total": 0, "privileged": 0, "with_findings": 0},
            }
        containers = audit_all(objs)
        return {
            "available": True, "reason": "", "fix_hint": "",
            "containers": containers,
            "counts": {
                "total": len(containers),
                "privileged": sum(1 for c in containers if c["privileged"]),
                "with_findings": sum(1 for c in containers if c["findings"]),
                # run_as_root(INFO) 는 거의 모든 컨테이너에 해당하므로 '조치 필요' 수치와 분리한다.
                # 대시보드와 알림은 이 값을 쓴다.
                "actionable": sum(1 for c in containers if actionable(c)),
            },
        }

    @property
    def last_error(self) -> str:
        return self._last_error
