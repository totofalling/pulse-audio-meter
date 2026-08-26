#!/usr/bin/env python3

import json
import math
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = 8765

SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2
CHUNK_FRAMES = 480

state = {
    "input_device": None,
    "output_device": None,

    "input_rms": -60.0,
    "input_peak": -60.0,
    "output_rms": -60.0,
    "output_peak": -60.0,

    "input_volume": 0.0,
    "output_volume": 0.0,

    "input_mute": False,
    "output_mute": False,

    "updated": 0,
}

meter_lock = threading.Lock()
input_process = None
output_process = None


def pactl(*args):
    result = subprocess.run(
        ["pactl", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "pactl failed"
        )

    return result.stdout


def get_sources():
    try:
        data = json.loads(
            pactl("-f", "json", "list", "sources")
        )
    except Exception:
        return []

    result = []

    for item in data:
        name = item.get("name")
        description = item.get("description") or name

        if name and not name.endswith(".monitor"):
            result.append({
                "name": name,
                "description": description,
            })

    return result


def get_sinks():
    try:
        data = json.loads(
            pactl("-f", "json", "list", "sinks")
        )
    except Exception:
        return []

    result = []

    for item in data:
        name = item.get("name")
        description = item.get("description") or name

        if name:
            result.append({
                "name": name,
                "description": description,
            })

    return result


def get_defaults():
    source = None
    sink = None

    try:
        info = pactl("info")

        for line in info.splitlines():
            if line.startswith("Default Source:"):
                source = line.split(":", 1)[1].strip()

            elif line.startswith("Default Sink:"):
                sink = line.split(":", 1)[1].strip()

    except Exception:
        pass

    return source, sink


def discover_devices():
    sources = get_sources()
    sinks = get_sinks()

    default_source, default_sink = get_defaults()

    source_names = [
        item["name"] for item in sources
    ]

    sink_names = [
        item["name"] for item in sinks
    ]

    if state["input_device"] not in source_names:
        state["input_device"] = (
            default_source
            if default_source in source_names
            else (
                source_names[0]
                if source_names
                else None
            )
        )

    if state["output_device"] not in sink_names:
        state["output_device"] = (
            default_sink
            if default_sink in sink_names
            else (
                sink_names[0]
                if sink_names
                else None
            )
        )


def get_volume(target, device):
    if not device:
        return 0.0

    try:
        command = (
            "get-source-volume"
            if target == "input"
            else "get-sink-volume"
        )

        text = pactl(command, device)

        for token in text.replace(",", " ").split():
            if token.endswith("%"):
                try:
                    return float(
                        token[:-1]
                    )
                except ValueError:
                    pass

    except Exception:
        pass

    return 0.0


def get_mute(target, device):
    if not device:
        return False

    try:
        command = (
            "get-source-mute"
            if target == "input"
            else "get-sink-mute"
        )

        text = pactl(command, device)

        return "yes" in text.lower()

    except Exception:
        return False


def refresh_controls():
    discover_devices()

    state["input_volume"] = round(
        get_volume(
            "input",
            state["input_device"],
        ),
        1,
    )

    state["output_volume"] = round(
        get_volume(
            "output",
            state["output_device"],
        ),
        1,
    )

    state["input_mute"] = get_mute(
        "input",
        state["input_device"],
    )

    state["output_mute"] = get_mute(
        "output",
        state["output_device"],
    )


def calculate_levels(raw):
    if not raw:
        return -60.0, -60.0

    count = len(raw) // 2

    if count <= 0:
        return -60.0, -60.0

    samples = struct.unpack(
        "<" + ("h" * count),
        raw[:count * 2],
    )

    peak = max(
        abs(sample)
        for sample in samples
    )

    sum_squares = sum(
        sample * sample
        for sample in samples
    )

    rms = math.sqrt(
        sum_squares / len(samples)
    )

    if rms <= 0:
        rms_db = -60.0
    else:
        rms_db = 20.0 * math.log10(
            rms / 32768.0
        )

    if peak <= 0:
        peak_db = -60.0
    else:
        peak_db = 20.0 * math.log10(
            peak / 32768.0
        )

    return (
        max(-60.0, min(0.0, rms_db)),
        max(-60.0, min(0.0, peak_db)),
    )


def stop_process(process):
    if process is None:
        return

    try:
        process.terminate()
        process.wait(timeout=1)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def start_meter(target, device):
    global input_process
    global output_process

    if not device:
        return

    if target == "input":
        old_process = input_process
    else:
        old_process = output_process

    stop_process(old_process)

    meter_device = device

    if target == "output":
        meter_device += ".monitor"

    try:
        process = subprocess.Popen(
            [
                "parec",
                "--device",
                meter_device,
                "--format=s16le",
                f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}",
                "--raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        process = None

    if target == "input":
        input_process = process
    else:
        output_process = process


def meter_worker(target):
    previous_device = None

    while True:
        try:
            device = (
                state["input_device"]
                if target == "input"
                else state["output_device"]
            )

            if device != previous_device:
                start_meter(
                    target,
                    device,
                )
                previous_device = device

            process = (
                input_process
                if target == "input"
                else output_process
            )

            if process is None or process.stdout is None:
                time.sleep(0.5)
                continue

            bytes_needed = (
                CHUNK_FRAMES
                * CHANNELS
                * SAMPLE_WIDTH
            )

            raw = process.stdout.read(
                bytes_needed
            )

            if not raw:
                start_meter(
                    target,
                    device,
                )
                time.sleep(0.1)
                continue

            rms, peak = calculate_levels(raw)

            with meter_lock:
                if target == "input":
                    state["input_rms"] = round(
                        rms,
                        1,
                    )
                    state["input_peak"] = round(
                        peak,
                        1,
                    )
                else:
                    state["output_rms"] = round(
                        rms,
                        1,
                    )
                    state["output_peak"] = round(
                        peak,
                        1,
                    )

                state["updated"] = time.time()

        except Exception:
            time.sleep(0.2)


def set_control(data):
    target = data.get("target")

    if target not in ("input", "output"):
        raise ValueError(
            "target must be input or output"
        )

    if target == "input":
        device = state["input_device"]
        set_volume_command = "set-source-volume"
        set_mute_command = "set-source-mute"
        set_default_command = "set-default-source"
    else:
        device = state["output_device"]
        set_volume_command = "set-sink-volume"
        set_mute_command = "set-sink-mute"
        set_default_command = "set-default-sink"

    if "device" in data:
        new_device = data["device"]

        if not new_device:
            raise ValueError(
                "device cannot be empty"
            )

        if target == "input":
            valid = [
                x["name"]
                for x in get_sources()
            ]
        else:
            valid = [
                x["name"]
                for x in get_sinks()
            ]

        if new_device not in valid:
            raise ValueError(
                "device not found"
            )

        pactl(
            set_default_command,
            new_device,
        )

        device = new_device

        if target == "input":
            state["input_device"] = device
        else:
            state["output_device"] = device

    if not device:
        raise ValueError(
            "no audio device selected"
        )

    if "volume" in data:
        volume = max(
            0,
            min(
                100,
                float(data["volume"]),
            ),
        )

        pactl(
            set_volume_command,
            device,
            f"{volume:.1f}%",
        )

    if "mute" in data:
        pactl(
            set_mute_command,
            device,
            "1" if data["mute"] else "0",
        )

    refresh_controls()


class Handler(BaseHTTPRequestHandler):

    def send_json(self, obj, status=200):
        body = json.dumps(
            obj
        ).encode()

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json",
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json({"ok": True})

    def do_GET(self):

        if self.path == "/health":
            self.send_json({
                "ok": True
            })
            return

        if self.path == "/state":
            self.send_json(
                dict(state)
            )
            return

        if self.path == "/devices":
            sources = get_sources()
            sinks = get_sinks()

            self.send_json({
                "inputs": sources,
                "outputs": sinks,
                "selected_input":
                    state["input_device"],
                "selected_output":
                    state["output_device"],
            })

            return

        self.send_json(
            {"error": "not found"},
            404,
        )

    def do_POST(self):

        if self.path != "/control":
            self.send_json(
                {"error": "not found"},
                404,
            )
            return

        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            raw = self.rfile.read(
                length
            )

            data = json.loads(
                raw or b"{}"
            )

            set_control(data)

            self.send_json(
                dict(state)
            )

        except Exception as exc:
            self.send_json(
                {
                    "error": str(exc)
                },
                500,
            )

    def log_message(self, *_):
        pass


def main():
    print(
        "=== PulseAudio Meter starting ===",
        flush=True,
    )

    discover_devices()
    refresh_controls()

    threading.Thread(
        target=meter_worker,
        args=("input",),
        daemon=True,
    ).start()

    threading.Thread(
        target=meter_worker,
        args=("output",),
        daemon=True,
    ).start()

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
