import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    if not isinstance(cmd, (list, tuple)) or not cmd:
        raise ValueError("run() expects a non-empty argument list")
    result = subprocess.run(list(cmd), cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def ensure_venv(project_root: Path, python_bin: str):
    venv_dir = project_root / ".venv"
    if not venv_dir.exists():
        run([python_bin, "-m", "venv", ".venv"], cwd=str(project_root))
    return venv_dir


def venv_python(venv_dir: Path, is_windows: bool):
    if is_windows:
        return str(venv_dir / "Scripts" / "python.exe")
    return str(venv_dir / "bin" / "python")


def install_requirements(project_root: Path, venv_py: str):
    run([venv_py, "-m", "pip", "install", "-r", "requirements.txt"], cwd=str(project_root))


def ensure_env(project_root: Path, venv_py: str):
    env_file = project_root / ".env"
    example = project_root / ".env.example"
    if env_file.exists() or not example.exists():
        created = env_file.exists()
    else:
        env_file.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        created = True

    doctor = project_root / "scripts" / "doctor.py"
    if doctor.exists():
        try:
            python_bin = venv_py if venv_py and Path(venv_py).exists() else sys.executable
            subprocess.run(
                [python_bin, str(doctor), "--write-env", f"--env-path={env_file}"],
                cwd=str(project_root),
                check=False,
            )
        except Exception:
            pass
    return created


def env_has_placeholders(project_root: Path):
    env_file = project_root / ".env"
    if not env_file.exists():
        return True
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        _, value = line.split("=", 1)
        normalized = value.strip().strip('"').strip("'").lower()
        if normalized.startswith("replace-me") or normalized.startswith("replace_with_"):
            return True
    return False


def systemd_quote(value: Path | str):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def install_systemd(project_root: Path, venv_py: str, service_name: str, start_service: bool):
    service_path = Path("/etc/systemd/system") / f"{service_name}.service"
    content = "\n".join([
        "[Unit]",
        "Description=CLIProxy Management Panel",
        "After=network.target",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={systemd_quote(project_root)}",
        f"ExecStart={systemd_quote(venv_py)} {systemd_quote(project_root / 'app.py')}",
        "Restart=always",
        "RestartSec=5",
        "Environment=PYTHONUNBUFFERED=1",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])
    service_path.write_text(content, encoding="utf-8")
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", service_name])
    if start_service:
        run(["systemctl", "restart", service_name])


def start_windows(project_root: Path, venv_py: str):
    app_path = project_root / "app.py"
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen([venv_py, str(app_path)], cwd=str(project_root), creationflags=creationflags)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-service", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--start", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-sudo", action="store_true")
    parser.add_argument("--service-name", default="cliproxy-panel")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    is_windows = os.name == "nt"
    python_bin = sys.executable

    venv_dir = ensure_venv(project_root, python_bin)
    venv_py = venv_python(venv_dir, is_windows)
    install_requirements(project_root, venv_py)
    ensure_env(project_root, venv_py)
    if env_has_placeholders(project_root):
        raise SystemExit("Please edit .env with real credentials and keys before starting or installing the service.")

    if not is_windows and args.install_service:
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            if not args.no_sudo and shutil.which("sudo"):
                sudo_args = [
                    "sudo",
                    python_bin,
                    str(Path(__file__).resolve()),
                    "--install-service",
                    f"--service-name={args.service_name}",
                    "--no-sudo",
                ]
                sudo_args.append("--start" if args.start else "--no-start")
                os.execvp("sudo", sudo_args)
            raise SystemExit("需要 root 权限安装 systemd 服务，请用 sudo 运行。")
        install_systemd(project_root, venv_py, args.service_name, args.start)
        return

    if args.start:
        if is_windows:
            start_windows(project_root, venv_py)
        else:
            run([venv_py, "app.py"], cwd=str(project_root))


if __name__ == "__main__":
    main()
