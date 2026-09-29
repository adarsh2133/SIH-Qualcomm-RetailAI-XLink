"""PORTAL-XLINK application entry point."""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from config import Settings
from database.connection import connect_database
from database.schema import initialize_database
from database.repository import Repository
from cameras.camera_manager import CameraManager


def _configure_logging(settings: Settings) -> None:
    """Configure file logging without making logging failures fatal."""
    try:
        log_path = Path(settings.logs_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_path), level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).exception("Unable to open configured log file")


def _headless_run(settings: Settings) -> None:
    root_dir = Path(settings.root_dir)
    root_dir.mkdir(parents=True, exist_ok=True)
    database_path = (Path(settings.root_dir) / "data" / "simulation" / "retail.db"
                     if settings.simulation else Path(settings.db_path))
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect_database(database_path)
    initialize_database(connection)
    repository = Repository(connection)
    if settings.simulation:
        repository.seed_demo_data()
    cameras = CameraManager.from_settings(settings)
    cameras.start_all()
    time.sleep(0.25)
    frames = cameras.read_all()
    statuses = cameras.statuses()
    cameras.close_all()
    online = sum(status.get("state") == "ONLINE" for status in statuses)
    mode = "SIMULATION/TEST" if settings.simulation else "LIVE HARDWARE"
    system = "ONLINE" if online == len(statuses) and online > 0 else ("DEGRADED" if online else "OFFLINE")
    print(f"PORTAL-XLINK headless {mode}: SYSTEM {system}, {online}/{len(statuses)} cameras ONLINE")
    print("METRICS: SIMULATION/TEST (isolated; not live data)" if settings.simulation
          else "METRICS: N/A (NO LIVE DATA; valid detections required)")
    for status in statuses:
        print(f"{status['camera_id']}: {status.get('state', 'OFFLINE')} | {status.get('error') or 'no error'}")
    from inference.model_factory import create_inference
    inference = create_inference(settings, settings.inference_backend)
    inference_status = inference.availability()
    print(
        "INFERENCE: "
        f"{inference.name} | {inference_status.get('state', 'UNAVAILABLE')} | "
        f"{inference_status.get('error') or 'no error'}"
    )
    connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="PORTAL-XLINK retail intelligence dashboard")
    parser.add_argument("--headless", action="store_true", help="run a local database and smoke-check without opening Tk")
    parser.add_argument("--simulation", action="store_true",
                        help="explicitly enable controlled simulation (never implied by headless)")
    parser.add_argument("--qualcomm-diagnostic", action="store_true",
                        help="report Qualcomm target/runtime/artifact availability without inference")
    parser.add_argument("--diagnose", action="store_true",
                        help="run a read-only live camera and inference pipeline diagnostic")
    parser.add_argument("--backend", choices=("ncnn", "yolo", "remote", "qaihub"),
                        help="select the inference backend (default: ncnn)")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="open the Windows Raspberry Pi connection setup wizard",
    )
    parser.add_argument("--serve-api", action="store_true",
                        help="run the Pi camera/YOLO pipeline and publish detections over HTTPS")
    parser.add_argument(
        "--re-pair",
        action="store_true",
        help="rotate the Pi API credential and issue a new local dashboard pairing code",
    )
    parser.add_argument("--qaihub-status", action="store_true",
                        help="show real Qualcomm AI Hub SDK/configuration status")
    parser.add_argument("--qaihub-devices", action="store_true",
                        help="query real Qualcomm AI Hub target devices")
    parser.add_argument("--qaihub-compile", action="store_true",
                        help="submit a real Qualcomm AI Hub compile job when configured")
    parser.add_argument("--qaihub-profile", action="store_true",
                        help="submit a real Qualcomm AI Hub profile job when configured")
    parser.add_argument("--qaihub-inference", action="store_true",
                        help="submit a real Qualcomm AI Hub inference job when configured")
    args = parser.parse_args()

    settings = Settings.from_env().with_headless(args.headless)
    if args.backend:
        settings = settings.with_inference_backend(args.backend)
    if args.setup:
        settings = settings.with_inference_backend("remote")
    if args.simulation:
        settings = settings.with_simulation(True)
    _configure_logging(settings)
    logging.getLogger(__name__).info("Starting application (headless=%s, simulation=%s)",
                                     settings.headless, settings.simulation)

    if args.qualcomm_diagnostic:
        from inference.diagnostics import print_qualcomm_diagnostic
        print_qualcomm_diagnostic(settings)
        return

    qaihub_action = next((name for name, enabled in (
        ("status", args.qaihub_status), ("devices", args.qaihub_devices),
        ("compile", args.qaihub_compile), ("profile", args.qaihub_profile),
        ("inference", args.qaihub_inference)) if enabled), None)
    if qaihub_action:
        from qaihub import workflow
        operation_name = {
            "compile": "compile_model",
            "profile": "profile_model",
        }.get(qaihub_action, qaihub_action)
        operation = getattr(workflow, operation_name)
        result = operation()
        import json
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    if args.diagnose:
        from inference.diagnostics import print_live_diagnostic
        print_live_diagnostic(settings)
        return

    if args.serve_api:
        from integration.pi_service import run_pi_service
        run_pi_service(settings)
        return
    if args.re_pair:
        if os.name == "nt":
            raise RuntimeError("--re-pair must be run locally on the Raspberry Pi")
        from integration.pi_identity import PairingManager
        from integration.pi_identity import ensure_tls_identity
        state_dir = os.getenv(
            "PORTAL_STATE_DIR", str(Path(settings.root_dir) / "data" / "runtime")
        )
        identity = ensure_tls_identity(state_dir)
        PairingManager(
            state_dir,
            token_override=os.getenv("PORTAL_API_TOKEN", ""),
            certificate_sha256=identity.certificate_sha256,
        ).rotate()
        print(
            "Pi API credential rotated. Restart the PORTAL-XLINK service, then "
            "pair the Windows dashboard with the new local approval code."
        )
        return

    if args.headless:
        _headless_run(settings)
        return

    if settings.inference_backend == "remote" and os.name == "nt":
        from desktop_config import apply_connection, load_connection
        from gui.setup_window import SetupWindow
        from integration.pi_provisioning import check_pi_health

        connection = None
        if not args.setup:
            try:
                connection = load_connection()
            except ValueError as exc:
                logging.getLogger(__name__).warning(
                    "Saved Pi connection settings need attention: %s", exc
                )
            if connection is None and os.getenv("PORTAL_API_TOKEN") and os.getenv(
                "PORTAL_REMOTE_API_URL"
            ):
                connection = {
                    "api_url": os.environ["PORTAL_REMOTE_API_URL"],
                    "token": os.environ["PORTAL_API_TOKEN"],
                }
            if connection is not None:
                try:
                    check_pi_health(connection)
                except (HTTPError, URLError, OSError, ValueError) as exc:
                    logging.getLogger(__name__).warning(
                        "Saved Pi connection needs setup or re-pairing: %s",
                        exc,
                    )
                    connection = None
        if args.setup or connection is None:
            setup = SetupWindow()
            setup.mainloop()
            connection = setup.connection
        if connection is None:
            return
        apply_connection(connection)

    from gui.main_window import MainWindow

    window = MainWindow(settings)
    window.mainloop()


if __name__ == "__main__":
    main()
