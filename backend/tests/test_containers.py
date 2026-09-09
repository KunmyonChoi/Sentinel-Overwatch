"""컨테이너 설정 점검 테스트. docker 를 절대 호출하지 않고, inspect 출력 모양의 dict 만 넣는다."""
from integrations.containers import audit_all, audit_container


def _inspect(**over) -> dict:
    """`docker inspect` 출력 1건의 최소 골격. 필요한 부분만 덮어쓴다."""
    obj = {
        "Id": "0123456789abcdef0123456789abcdef",
        "Name": "/app",
        "Image": "sha256:deadbeef",
        "Config": {"Image": "nginx:1.27", "User": "10001"},
        "HostConfig": {
            "Privileged": False,
            "NetworkMode": "bridge",
            "PidMode": "",
            "RestartPolicy": {"Name": "unless-stopped"},
            "Binds": [],
            "CapAdd": None,
            "PortBindings": {},
        },
        "Mounts": [],
        "NetworkSettings": {"Ports": {}},
    }
    for key, value in over.items():
        if key in ("Config", "HostConfig", "NetworkSettings") and isinstance(value, dict):
            obj[key] = {**obj[key], **value}
        else:
            obj[key] = value
    return obj


def _codes(res: dict) -> list[str]:
    return [f["code"] for f in res["findings"]]


def _by_code(res: dict, code: str) -> dict:
    return next(f for f in res["findings"] if f["code"] == code)


def test_privileged_is_critical():
    res = audit_container(_inspect(
        Name="/buildx_buildkit_builder0",
        HostConfig={"Privileged": True, "RestartPolicy": {"Name": "always"}},
    ))
    assert res["privileged"] is True
    assert res["id"] == "0123456789ab" and res["name"] == "buildx_buildkit_builder0"
    assert res["image"] == "nginx:1.27" and res["restart"] == "always"
    f = _by_code(res, "privileged")
    assert f["severity"] == "CRITICAL"
    assert "docker buildx stop buildx_buildkit_builder0" in f["fix_ko"]


def test_docker_sock_mount_is_critical():
    res = audit_container(_inspect(Mounts=[
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True},
    ]))
    f = _by_code(res, "docker_sock")
    assert f["severity"] == "CRITICAL"
    assert "root" in f["detail_ko"]          # 호스트 root 와 동등하다는 사실을 반드시 말한다
    # HostConfig.Binds 문자열 형태로도 같은 판정이 나와야 한다
    res2 = audit_container(_inspect(HostConfig={"Binds": ["/run/docker.sock:/run/docker.sock:rw"]}))
    assert "docker_sock" in _codes(res2)


def test_port_published_on_all_interfaces_is_warning():
    res = audit_container(_inspect(NetworkSettings={"Ports": {
        "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
        "9000/tcp": None,      # 공개되지 않은 포트는 null 로 나온다
    }}))
    f = _by_code(res, "port_all_interfaces")
    assert f["severity"] == "WARNING"
    assert "8080" in f["detail_ko"]                    # 포트를 반드시 지목한다
    assert "-p 127.0.0.1:8080:8080" in f["fix_ko"]
    assert "ufw" in f["fix_ko"] or "ufw" in f["detail_ko"]


def test_loopback_published_port_is_not_flagged():
    res = audit_container(_inspect(NetworkSettings={"Ports": {
        "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5432"}],
    }}))
    assert "port_all_interfaces" not in _codes(res)


def test_host_network_replaces_port_finding():
    res = audit_container(_inspect(
        HostConfig={"NetworkMode": "host"},
        NetworkSettings={"Ports": {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}},
    ))
    codes = _codes(res)
    assert "host_network" in codes
    assert "port_all_interfaces" not in codes          # host 네트워크에 이미 포함된 내용이므로 중복 보고하지 않는다
    assert _by_code(res, "host_network")["severity"] == "WARNING"


def test_host_pid_is_warning():
    res = audit_container(_inspect(HostConfig={"PidMode": "host"}))
    assert _by_code(res, "host_pid")["severity"] == "WARNING"


def test_cap_add_names_the_capability():
    res = audit_container(_inspect(HostConfig={"CapAdd": ["SYS_ADMIN"]}))
    f = _by_code(res, "cap_add")
    assert f["severity"] == "WARNING"
    assert "SYS_ADMIN" in f["title_ko"] and "SYS_ADMIN" in f["detail_ko"]
    # 무해한 케이퍼빌리티만 있으면 보고하지 않는다
    assert "cap_add" not in _codes(audit_container(_inspect(HostConfig={"CapAdd": ["CHOWN"]})))


def test_run_as_root_is_info_only():
    res = audit_container(_inspect(Config={"User": ""}))
    f = _by_code(res, "run_as_root")
    assert f["severity"] == "INFO"
    assert "run_as_root" not in _codes(audit_container(_inspect(Config={"User": "1000:1000"})))


def test_clean_container_has_no_findings():
    res = audit_container(_inspect(
        Name="/secdash-redis",
        Config={"Image": "redis:7", "User": "999"},
        NetworkSettings={"Ports": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6379"}]}},
    ))
    assert res["findings"] == []
    assert res["privileged"] is False and res["name"] == "secdash-redis"


def test_malformed_objects_do_not_raise():
    for bad in ({}, {"Id": None, "HostConfig": "nope", "Mounts": "nope"},
                {"NetworkSettings": {"Ports": {"x": [{"HostIp": None}]}}},
                {"Config": {"User": None}, "HostConfig": {"CapAdd": [None, 5]}}):
        res = audit_container(bad)
        assert isinstance(res["findings"], list) and isinstance(res["name"], str)
    assert audit_all([]) == []
    assert audit_all(None) == []


def test_audit_all_puts_findings_first():
    rows = audit_all([
        _inspect(Id="aaaaaaaaaaaa1111", Name="/clean", Config={"User": "999"}),
        _inspect(Id="bbbbbbbbbbbb2222", Name="/rootish", Config={"User": "root"}),
        _inspect(Id="cccccccccccc3333", Name="/danger", HostConfig={"Privileged": True}),
    ])
    assert [r["name"] for r in rows] == ["danger", "rootish", "clean"]
    assert rows[-1]["findings"] == []
