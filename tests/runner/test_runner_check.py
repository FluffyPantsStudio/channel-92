"""`ping`: both hosts answer with their GPU, ffmpeg is there, Python reads UTF-8."""

from __future__ import annotations

from atomic_flix.runner.check import check_hosts


def _which(name: str) -> str:
    return f"C:/tools/{name}.exe"


def test_two_live_hosts_pass_and_name_their_gpus(fake_hosts):
    fakes = fake_hosts(2)
    account = check_hosts([f.host for f in fakes], which=_which, utf8_mode=True)
    assert account.ok
    text = "\n".join(account.lines)
    assert "Fake GPU 0" in text and "Fake GPU 1" in text and "24 GB" in text


def test_a_host_that_does_not_answer_fails_and_is_named(fake_hosts):
    (fake,) = fake_hosts(1)
    dead = "127.0.0.1:9"
    account = check_hosts([fake.host, dead], which=_which, utf8_mode=True, timeout_s=1.0)
    assert not account.ok
    assert any(dead in line for line in account.lines)


def test_missing_ffprobe_and_no_utf8_mode_fail(fake_hosts):
    (fake,) = fake_hosts(1)
    account = check_hosts([fake.host], which=lambda name: None if name == "ffprobe" else _which(name),
                         utf8_mode=False, windows=True)
    assert not account.ok
    text = "\n".join(account.lines)
    assert "ffprobe" in text and "UTF-8" in text


def test_check_never_queues_anything(fake_hosts):
    (fake,) = fake_hosts(1)
    check_hosts([fake.host], which=_which, utf8_mode=True)
    assert fake.submitted == []
    assert all(method == "GET" for method, _ in fake.requests)
