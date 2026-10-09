"""`dbee watch --config` (what the installed service runs) starts and sleeps: seen
live, a verb's local import shadowed a name and the service crash-looped at start."""
import queue

import dbee.__main__ as cli


class _Interrupted(queue.Queue):
    def get(self, *a, **kw):
        raise KeyboardInterrupt          # the person stops it as soon as it sleeps


def test_the_service_command_starts_and_sleeps(tmp_path, monkeypatch, capsys):
    log = tmp_path / "app.log"
    log.write_text("")
    cfg = tmp_path / "dbee.toml"
    cfg.write_text(f'[mind]\nspec = "file:{tmp_path / "seat"}"\n[[watch]]\nfile = "{log}"\n'
                   f'[doctor]\nhome = "{tmp_path / "home"}"\n')
    monkeypatch.setattr(cli, "Queue", _Interrupted)
    assert cli.main(["watch", "--config", str(cfg)]) == 0
    assert "dbee sleeps on" in capsys.readouterr().out
