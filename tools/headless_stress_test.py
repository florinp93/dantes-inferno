#!/usr/bin/env python3
"""
Headless automated stress-test harness for the ReXGlue-ported Dante's Inferno.

What this does
--------------
* Launches the recompiled `dantes_inferno.exe` with stress-friendly cvars:
    --headless        skip XAM UI dialogs (so automation never blocks on a
                      guest MessageBox waiting for input)
    --audio_mute      no audio device activity
    --no-vsync        unlock the guest vblank worker (~1000 Hz guest tick);
                      the SDK has no --turbo/--framerate 0/--no-render flag,
                      so --no-vsync is the closest available "fast forward"
    --window_width/--window_height  tiny window (a window is always created
                      on Windows; the SDK has no display-less mode)
    --log_level=trace --log_file=<run.log>  full trace logging
* Attaches to the process as a Win32 debugger so it can intercept fatal
  exceptions (access violations, etc.), capture a minidump at the moment of
  the crash, and record the exact exception code + faulting address.
* Runs a monkey-testing thread (Option A) that posts semi-randomized
  keyboard/mouse events to the game window. The app's MnK driver translates
  these into a virtual Xbox 360 controller, so the monkey exercises real
  gameplay/input paths.
* Repeats for N runs, each bounded by a timeout (hang detection).
* Parses every run log for crash/assert/error signatures, correlates with the
  minidump's exception record + faulting module, and writes bugs_found.md.

Usage
-----
    python tools/headless_stress_test.py --runs 2 --duration 60

Run from the project root so `--game_data_root=game` resolves. Do not touch
the keyboard/mouse while a run is in progress (the monkey posts to the game
window via PostMessage, which is background-safe, but focus changes can still
interfere).

Outputs (under ./test by default):
    headless_test_run.log   combined harness log
    run_<n>.log             per-run game trace log
    minidumps/run_<n>.dmp   minidump captured at crash (if any)
    bugs_found.md           final analysis report
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import datetime as _dt
import os
import random
import re
import struct
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Win32 bindings (kernel32 / dbghelp)
# ---------------------------------------------------------------------------

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)

DEBUG_PROCESS = 0x00000001
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_CONSOLE = 0x00000010
INFINITE = 0xFFFFFFFF
STILL_ACTIVE = 259

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205

# Win32 NT status codes that indicate a crash (subset).
NT_STATUS_MAP = {
    0x80000003: "BREAKPOINT (debug / initial breakpoint)",
    0x80000004: "SINGLE_STEP (debug)",
    0xC0000005: "ACCESS_VIOLATION",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000025: "NONCONTINUABLE_EXCEPTION",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000374: "HEAP_CORRUPTION",
    0xC0000409: "STACK_BUFFER_OVERRUN (FAILFAST)",
    0xC000041D: "UNHANDLED_EXCEPTION_CALLBACK",
    0x40000015: "FATAL_APP_EXIT",
    0xE06D7363: "C++ EXCEPTION (msvcrt)",
    0xE0434352: "CLR_EXCEPTION",
}

# Exception codes that are genuinely fatal when they reach the debugger
# first-chance: we capture a minidump immediately and let the process die.
FATAL_FIRST_CHANCE = {
    0xC0000005, 0xC000001D, 0xC0000025, 0xC0000094, 0xC00000FD,
    0xC0000374, 0xC0000409, 0xC000041D, 0x40000015,
}
# Debug / control-flow exceptions that are normally first-chance and swallowed
# by the program's own SEH (asserts, the initial debug breakpoint, C++ throws).
# We DBG_CONTINUE them on first chance and only dump on second chance.
DEBUG_EXCEPTIONS = {0x80000003, 0x80000004, 0xE06D7363, 0xE0434352}

# MiniDumpType flags
MiniDumpNormal = 0x00000000
MiniDumpWithThreadInfo = 0x00001000
MiniDumpWithIndirectlyReferencedMemory = 0x00000040


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


# DEBUG_EVENT on x64: 3 DWORDs + 4 pad + union(256). We keep the union as raw
# bytes and parse the members we care about (exception / exit process) by hand.
class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [
        ("dwDebugEventCode", wintypes.DWORD),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
        ("_pad", wintypes.DWORD),
        ("u", ctypes.c_byte * 256),
    ]


# Debug event codes
EXCEPTION_DEBUG_EVENT = 1
CREATE_THREAD_DEBUG_EVENT = 2
CREATE_PROCESS_DEBUG_EVENT = 3
EXIT_THREAD_DEBUG_EVENT = 4
EXIT_PROCESS_DEBUG_EVENT = 5
LOAD_DLL_DEBUG_EVENT = 6
UNLOAD_DLL_DEBUG_EVENT = 7
OUTPUT_DEBUG_STRING_EVENT = 8
RIP_EVENT = 9

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001

# EXCEPTION_RECORD on x64 (parsed from the union bytes):
#   DWORD ExceptionCode
#   DWORD ExceptionFlags
#   PVOID ExceptionRecord   (8)
#   PVOID ExceptionAddress  (8)
#   DWORD NumberParameters
#   (4 pad)
#   ULONG_PTR[15]  (120)
# Total EXCEPTION_RECORD = 152 bytes; then DWORD dwFirstChance at offset 152.
EXC_FMT = "<IIQQI"
EXC_FIRST_CHANCE_OFFSET = 152  # dwFirstChance follows the 152-byte EXCEPTION_RECORD


def _setup_prototypes():
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL

    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD

    kernel32.WaitForDebugEvent.argtypes = [ctypes.POINTER(DEBUG_EVENT), wintypes.DWORD]
    kernel32.WaitForDebugEvent.restype = wintypes.BOOL

    kernel32.ContinueDebugEvent.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
    kernel32.ContinueDebugEvent.restype = wintypes.BOOL

    kernel32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]
    kernel32.DebugSetProcessKillOnExit.restype = wintypes.BOOL

    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    # MiniDumpWriteDump
    dbghelp.MiniDumpWriteDump.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL


_setup_prototypes()

# EnumWindows for HWND discovery
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int


def find_game_hwnd(title_prefix: str, timeout: float = 20.0) -> int | None:
    """Find a top-level window whose title starts with `title_prefix`."""
    deadline = time.time() + timeout
    found: list[int] = []

    def _enum(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value.lower().startswith(title_prefix.lower()):
            found.append(int(hwnd))
        return True

    while time.time() < deadline:
        found.clear()
        user32.EnumWindows(WNDENUMPROC(_enum), 0)
        if found:
            return found[0]
        time.sleep(0.25)
    return None


# ---------------------------------------------------------------------------
# Monkey input (Option A)
# ---------------------------------------------------------------------------

# Virtual-key set mapped (via the app's MnK driver) to virtual gamepad actions.
# See src/dantes_inferno_app.h for the keybind table.
MONKEY_KEYS = [
    0x57,  # W  (lstick up / move)
    0x53,  # S  (lstick down)
    0x41,  # A  (lstick left)
    0x44,  # D  (lstick right)
    0x20,  # Space  (A / jump / interact)
    0x46,  # F  (B / heavy attack)
    0x45,  # E  (Y / grab)
    0x51,  # Q  (LB / block)
    0x58,  # X  (lstick press)
    0x52,  # R  (rstick press)
    0x09,  # Tab (Back)
    0x1B,  # Esc (Start)
    0x10,  # Shift (LT)
    0x11,  # Ctrl  (RT)
    0x26,  # Up
    0x28,  # Down
    0x25,  # Left
    0x27,  # Right
]


def _make_lparam(x: int, y: int) -> int:
    return (y << 16) | (x & 0xFFFF)


class Monkey:
    """Posts randomized keyboard/mouse events to a target HWND via PostMessage.

    Background-safe: does not require the window to be in the foreground. SDL3's
    Win32 window proc consumes WM_KEYDOWN/WM_MOUSEMOVE, and the app's MnK
    driver translates them into a virtual Xbox 360 controller."""

    def __init__(self, hwnd_getter, interval_ms: int, rng: random.Random):
        self._hwnd_getter = hwnd_getter
        self._interval = interval_ms / 1000.0
        self._rng = rng
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.actions = 0

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self):
        while not self._stop.is_set():
            hwnd = self._hwnd_getter()
            if hwnd:
                self._step(hwnd)
            time.sleep(self._interval)

    def _step(self, hwnd: int):
        roll = self._rng.random()
        if roll < 0.6:
            # key tap (down + up) on a random key
            vk = self._rng.choice(MONKEY_KEYS)
            lparam_down = (1 << 30) | (self._rng.randint(1, 0xFFFF))
            user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam_down)
            time.sleep(self._rng.uniform(0.02, 0.09))
            user32.PostMessageW(hwnd, WM_KEYUP, vk, (1 << 31) | (1 << 30))
            self.actions += 1
        elif roll < 0.8:
            # mouse move + click somewhere in the small window
            x, y = self._rng.randint(10, 300), self._rng.randint(10, 160)
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, _make_lparam(x, y))
            time.sleep(self._rng.uniform(0.02, 0.06))
            user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 0x0001, _make_lparam(x, y))
            time.sleep(self._rng.uniform(0.03, 0.08))
            user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, _make_lparam(x, y))
            self.actions += 1
        else:
            # brief multi-key hold (movement combo)
            keys = self._rng.sample(MONKEY_KEYS[:4], k=self._rng.randint(1, 3))
            for vk in keys:
                user32.PostMessageW(hwnd, WM_KEYDOWN, vk, (1 << 30))
            time.sleep(self._rng.uniform(0.15, 0.45))
            for vk in keys:
                user32.PostMessageW(hwnd, WM_KEYUP, vk, (1 << 31) | (1 << 30))
            self.actions += 1


# ---------------------------------------------------------------------------
# Debugger-attached run loop
# ---------------------------------------------------------------------------


class RunResult:
    def __init__(self, index: int):
        self.index = index
        self.start_time = 0.0
        self.end_time = 0.0
        self.exit_code: int | None = None
        self.outcome = "unknown"  # "clean_exit" | "crash" | "hang" | "launch_failed"
        self.exception_code: int | None = None
        self.exception_address: int | None = None
        self.faulting_module: str | None = None
        self.minidump_path: str | None = None
        self.log_path: str | None = None
        self.hwnd: int | None = None
        self.monkey_actions = 0
        self.last_log_lines: list[str] = []
        self.signatures: list[str] = []

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def classify_exit(self) -> str:
        if self.exit_code is None:
            return "no exit"
        if self.exit_code == 0:
            return "clean exit (0)"
        name = NT_STATUS_MAP.get(self.exit_code)
        if name:
            return f"crash: {name} (0x{self.exit_code:08X})"
        if self.exit_code & 0x80000000:
            return f"crash: NT status 0x{self.exit_code:08X}"
        return f"non-zero exit (0x{self.exit_code:X})"


def _parse_exception(union_bytes: bytes) -> tuple[int, int]:
    code, _flags, _rec, addr, _nparams = struct.unpack_from(EXC_FMT, union_bytes, 0)
    return code, addr


def _write_minidump(h_process, pid: int, dump_path: Path, exc_code: int | None,
                    thread_id: int | None) -> bool:
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    h_file = kernel32.CreateFileW(
        str(dump_path), 0x40000000, 0, None, 2, 0x80, None  # GENERIC_WRITE, CREATE_ALWAYS
    )
    if not h_file or h_file == wintypes.HANDLE(-1).value:
        return False
    try:
        dump_type = MiniDumpNormal | MiniDumpWithThreadInfo
        ok = dbghelp.MiniDumpWriteDump(h_process, pid, h_file, dump_type, None, None, None)
        return bool(ok)
    finally:
        kernel32.CloseHandle(h_file)


def run_one(index: int, exe: Path, game_root: str, out_dir: Path,
            duration: float, monkey: bool, input_interval_ms: int,
            rng_seed: int, log) -> RunResult:
    res = RunResult(index)
    res.start_time = time.time()
    res.log_path = str(out_dir / f"run_{index}.log")

    cmd = [
        str(exe),
        "--headless",
        "--audio_mute",
        "--no-vsync",
        "--window_width=320",
        "--window_height=180",
        "--log_level=trace",
        f"--log_file={res.log_path}",
        f"--game_data_root={game_root}",
    ]
    log(f"[run {index}] launch: {' '.join(cmd)}")

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.dwFlags = 0x00000001  # STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE -> let SDL create the window; we don't force-show
    pi = PROCESS_INFORMATION()

    cmd_line = " ".join(f'"{a}"' if " " in a else a for a in cmd)
    ok = kernel32.CreateProcessW(
        None, ctypes.create_unicode_buffer(cmd_line), None, None, False,
        DEBUG_PROCESS | CREATE_NEW_CONSOLE, None, None,
        ctypes.byref(si), ctypes.byref(pi),
    )
    if not ok:
        err = ctypes.get_last_error()
        res.outcome = "launch_failed"
        res.exit_code = err
        log(f"[run {index}] CreateProcessW failed: WinError {err}")
        res.end_time = time.time()
        return res

    h_process = pi.hProcess
    h_thread = pi.hThread
    pid = pi.dwProcessId
    kernel32.DebugSetProcessKillOnExit(True)
    kernel32.ResumeThread(h_thread)
    kernel32.CloseHandle(h_thread)

    # HWND discovery + monkey
    hwnd_holder: dict[str, int | None] = {"hwnd": None}

    def _hwnd_getter():
        if hwnd_holder["hwnd"] is None:
            hwnd_holder["hwnd"] = find_game_hwnd("dantes_inferno", timeout=duration)
        return hwnd_holder["hwnd"]

    mk = Monkey(_hwnd_getter, input_interval_ms, random.Random(rng_seed + index)) if monkey else None
    if mk:
        mk.start()

    # Watchdog for hang detection. Try a graceful WM_CLOSE first so the SDK's
    # logger flushes its buffers (TerminateProcess would lose buffered log
    # lines), then fall back to TerminateProcess.
    watchdog_state = {"fired": False, "graceful": False}

    def _watchdog():
        if time.time() - res.start_time < duration:
            return
        watchdog_state["fired"] = True
        hwnd = hwnd_holder["hwnd"]
        log(f"[run {index}] watchdog: timeout {duration}s reached, requesting shutdown")
        if hwnd:
            # WM_CLOSE -> let the app run its OnShutdown / logger teardown.
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(3.0)
        # If still alive, hard-kill.
        code = wintypes.DWORD(0)
        if kernel32.GetExitCodeProcess(h_process, ctypes.byref(code)) and code.value == STILL_ACTIVE:
            log(f"[run {index}] process did not exit on WM_CLOSE, terminating")
            kernel32.TerminateProcess(h_process, 0xDEADBEEF)
        else:
            watchdog_state["graceful"] = True

    timer = threading.Timer(duration, _watchdog)
    timer.start()

    dump_path = out_dir / "minidumps" / f"run_{index}.dmp"
    captured_dump = False
    first_chance_seen: set[int] = set()

    try:
        ev = DEBUG_EVENT()
        while True:
            if not kernel32.WaitForDebugEvent(ctypes.byref(ev), 500):
                # No event in 500ms; check if process still alive.
                code = wintypes.DWORD(0)
                if kernel32.GetExitCodeProcess(h_process, ctypes.byref(code)):
                    if code.value != STILL_ACTIVE:
                        res.exit_code = code.value
                        break
                continue

            code = ev.dwDebugEventCode
            tid = ev.dwThreadId

            if code == EXIT_PROCESS_DEBUG_EVENT:
                exit_code = struct.unpack_from("<I", ev.u, 0)[0]
                res.exit_code = exit_code
                kernel32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
                break

            elif code == EXCEPTION_DEBUG_EVENT:
                exc_code, exc_addr = _parse_exception(bytes(ev.u))
                first_chance = struct.unpack_from("<I", ev.u, EXC_FIRST_CHANCE_OFFSET)[0] == 1

                if exc_code in DEBUG_EXCEPTIONS:
                    # First-chance debug/C++ exceptions (initial breakpoint,
                    # asserts, throws) are normally swallowed by the program's
                    # own SEH. Continue them; only dump if they come back as
                    # second-chance (genuinely unhandled).
                    if not first_chance and not captured_dump:
                        res.exception_code = exc_code
                        res.exception_address = exc_addr
                        if _write_minidump(h_process, pid, dump_path, exc_code, tid):
                            res.minidump_path = str(dump_path)
                            captured_dump = True
                            log(f"[run {index}] captured minidump (2nd-chance debug exc): "
                                f"{dump_path} (exc=0x{exc_code:08X} addr=0x{exc_addr:016X})")
                    kernel32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
                elif exc_code in FATAL_FIRST_CHANCE:
                    # Genuinely fatal: capture dump on first sight, then let the
                    # default unhandled-exception path terminate the process.
                    if not captured_dump:
                        res.exception_code = exc_code
                        res.exception_address = exc_addr
                        if _write_minidump(h_process, pid, dump_path, exc_code, tid):
                            res.minidump_path = str(dump_path)
                            captured_dump = True
                            log(f"[run {index}] captured minidump: {dump_path} "
                                f"(exc=0x{exc_code:08X} addr=0x{exc_addr:016X})")
                    kernel32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId,
                                                DBG_EXCEPTION_NOT_HANDLED)
                else:
                    # Unknown exception: continue first-chance, dump second-chance.
                    if not first_chance and not captured_dump:
                        res.exception_code = exc_code
                        res.exception_address = exc_addr
                        if _write_minidump(h_process, pid, dump_path, exc_code, tid):
                            res.minidump_path = str(dump_path)
                            captured_dump = True
                    kernel32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId,
                                                DBG_CONTINUE if first_chance else DBG_EXCEPTION_NOT_HANDLED)

            elif code == OUTPUT_DEBUG_STRING_EVENT:
                kernel32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)

            else:
                kernel32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)

    except Exception:
        log(f"[run {index}] debugger loop error:\n{traceback.format_exc()}")
    finally:
        timer.cancel()
        if mk:
            mk.stop()
            res.monkey_actions = mk.actions
        res.hwnd = hwnd_holder["hwnd"]

        # If we never got an exit code via the debug loop, read it now.
        if res.exit_code is None:
            code = wintypes.DWORD(0)
            if kernel32.GetExitCodeProcess(h_process, ctypes.byref(code)):
                res.exit_code = code.value
        kernel32.CloseHandle(h_process)

    res.end_time = time.time()

    if watchdog_state["fired"]:
        # Distinguish a healthy game loop (still rendering) from a true stall
        # by checking the timestamp of the last log line vs. termination time.
        last_ts = _last_log_timestamp(res.log_path)
        if last_ts is not None and (res.end_time - last_ts) <= 6.0:
            res.outcome = "running_at_timeout"  # process was making progress
        else:
            res.outcome = "hang"  # no recent log activity -> likely a true stall
    elif res.exit_code == 0:
        res.outcome = "clean_exit"
    elif res.exit_code == 0xDEADBEEF:
        res.outcome = "hang"
    elif res.exit_code is not None and (res.exit_code & 0x80000000):
        res.outcome = "crash"
    else:
        res.outcome = "clean_exit" if res.exit_code == 0 else "nonzero_exit"

    # Tail the run log for context.
    res.last_log_lines = _tail(res.log_path, 60)
    res.signatures = _scan_signatures(res.log_path)

    log(f"[run {index}] outcome={res.outcome} exit=0x{(res.exit_code or 0):08X} "
        f"dur={res.duration:.1f}s monkey_actions={res.monkey_actions} "
        f"hwnd={res.hwnd}")
    return res


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

SIGNATURE_PATTERNS = [
    re.compile(r"\bACCESS_VIOLATION\b", re.I),
    re.compile(r"\bSIGSEGV\b|\bSEGFAULT\b", re.I),
    re.compile(r"\bassert(?:_not_null|ion)?\b.*fail", re.I),
    re.compile(r"\bFATAL\b", re.I),
    re.compile(r"\bCRASH\b", re.I),
    re.compile(r"REXLOG_ERROR", re.I),
    re.compile(r"\bnull\b.*\bpointer\b|\bnullptr\b.*\bderef", re.I),
    re.compile(r"\bunimplemented\b|\bnot implemented\b", re.I),
    re.compile(r"\bXSTATUS\b.*0x[0-9A-Fa-f]{8}|\bXFAILED\b", re.I),
    re.compile(r"\bout of range\b|\bbad_alloc\b|\bbad_function_call\b", re.I),
    re.compile(r"\bstack overflow\b|\bheap corruption\b", re.I),
    re.compile(r"exception code\s*0x[0-9A-Fa-f]{8}", re.I),
]


def _scan_signatures(log_path: str | None) -> list[str]:
    if not log_path or not os.path.exists(log_path):
        return []
    hits: list[str] = []
    seen = set()
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                for pat in SIGNATURE_PATTERNS:
                    if pat.search(line):
                        key = pat.pattern
                        if key not in seen:
                            seen.add(key)
                            hits.append(line.strip()[:300])
    except Exception:
        pass
    return hits


def _tail(log_path: str | None, n: int) -> list[str]:
    if not log_path or not os.path.exists(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip("\n")[:300] for l in lines[-n:]]
    except Exception:
        return []


_LOG_TS_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]")


def _last_log_timestamp(log_path: str | None) -> float | None:
    """Parse the timestamp of the last log line into epoch seconds. Used to tell
    a healthy game loop (recent log activity) from a true stall."""
    if not log_path or not os.path.exists(log_path):
        return None
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            m = _LOG_TS_RE.search(line)
            if m:
                return _dt.datetime.fromisoformat(m.group(1)).timestamp()
    except Exception:
        pass
    return None


def _parse_minidump(dump_path: str) -> dict:
    """Best-effort extraction of exception record + faulting module from a
    minidump using the `minidump` Python package (pure Python)."""
    info: dict = {"exception_code": None, "exception_address": None,
                  "faulting_module": None, "thread_count": None, "modules": []}
    try:
        from minidump.minidumpfile import MinidumpFile
    except Exception as e:
        info["error"] = f"minidump package unavailable: {e}"
        return info
    try:
        mf = MinidumpFile.parse(dump_path)
        if mf.exception and getattr(mf.exception, "exception_records", None):
            rec = mf.exception.exception_records[0].ExceptionRecord
            if rec is not None:
                raw = getattr(rec, "ExceptionCode_raw", None)
                info["exception_code"] = f"0x{raw:08X}" if raw is not None else str(rec.ExceptionCode)
                addr = getattr(rec, "ExceptionAddress", None)
                if addr is not None:
                    info["exception_address"] = f"0x{addr:016X}"
                if addr is not None and mf.modules and getattr(mf.modules, "modules", None):
                    for mod in mf.modules.modules:
                        base = getattr(mod, "baseaddress", 0) or 0
                        end = getattr(mod, "endaddress", base) or base
                        if base <= addr < end:
                            info["faulting_module"] = mod.name
                            break
        if mf.threads and getattr(mf.threads, "threads", None):
            info["thread_count"] = len(mf.threads.threads)
        if mf.modules and getattr(mf.modules, "modules", None):
            info["modules"] = [m.name for m in mf.modules.modules if m.name][:32]
    except Exception as e:
        info["error"] = f"parse failed: {e}"
    return info


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(results: list[RunResult], out_dir: Path, harness_log: Path):
    crashes = [r for r in results if r.outcome == "crash"]
    hangs = [r for r in results if r.outcome == "hang"]
    running = [r for r in results if r.outcome == "running_at_timeout"]
    cleans = [r for r in results if r.outcome in ("clean_exit", "nonzero_exit")]
    md = out_dir / "bugs_found.md"
    lines: list[str] = []
    lines.append("# Headless Stress Test Report")
    lines.append("")
    lines.append(f"Generated: {_dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Harness log: `{harness_log}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Runs: **{len(results)}**")
    lines.append(f"- Crashes: **{len(crashes)}**")
    lines.append(f"- True hangs (no log progress at timeout): **{len(hangs)}**")
    lines.append(f"- Running normally at timeout (game loop, not a bug): **{len(running)}**")
    lines.append(f"- Clean / non-zero exits: **{len(cleans)}**")
    lines.append("")
    lines.append("## Runtime configuration")
    lines.append("")
    lines.append("The recompiled `dantes_inferno.exe` was launched with these cvars "
                 "(every ReXGlue cvar is auto-exposed as a `--cvar=value` CLI flag):")
    lines.append("")
    lines.append("| Flag | Purpose |")
    lines.append("|------|---------|")
    lines.append("| `--headless` | Skips XAM UI dialogs so automation never blocks on a guest MessageBox. |")
    lines.append("| `--audio_mute` | Disables audio output. |")
    lines.append("| `--no-vsync` | Unlocks the guest vblank worker to ~1000 Hz guest tick (closest available to a 'turbo' mode; the SDK has no `--turbo`/`--framerate 0`/`--no-render` flag). |")
    lines.append("| `--window_width=320 --window_height=180` | Smallest viable window. A window is always created on Windows (SDL3); the SDK has no display-less mode. |")
    lines.append("| `--log_level=trace --log_file=...` | Full trace logging for post-crash analysis. |")
    lines.append("| `--game_data_root=game` | Resolves the guest `game:\\` VFS to `./game`. |")
    lines.append("")
    lines.append("Input coverage (Option A — monkey testing): a background thread posted "
                 "semi-randomized `WM_KEYDOWN`/`WM_MOUSEMOVE` events to the game window "
                 "via `PostMessageW`. The app's MnK driver (enabled in "
                 "`src/dantes_inferno_app.h`) translates these into a virtual Xbox 360 "
                 "controller, exercising real gameplay/input paths. Scene/level warp "
                 "iteration (Option B) was **not** used because it requires reverse "
                 "engineering of the generated game code (per `AGENTS.md`, RE work is "
                 "still pending).")
    lines.append("")
    lines.append("Crash interception: the harness attached as a Win32 debugger "
                 "(`DEBUG_PROCESS`) and called `MiniDumpWriteDump` at the first fatal "
                 "exception, recording the NT status code, faulting address, and (via "
                 "the `minidump` package) the faulting module.")
    lines.append("")

    lines.append("## Per-run results")
    lines.append("")
    lines.append("| Run | Outcome | Exit code | Duration | Exc. code | Exc. address | Faulting module | Monkey actions |")
    lines.append("|-----|---------|-----------|----------|-----------|--------------|-----------------|----------------|")
    for r in results:
        exc = f"0x{r.exception_code:08X}" if r.exception_code else "-"
        addr = f"0x{r.exception_address:016X}" if r.exception_address else "-"
        ec = f"0x{(r.exit_code or 0):08X}" if r.exit_code is not None else "-"
        lines.append(f"| {r.index} | {r.outcome} | {ec} | {r.duration:.1f}s | {exc} | {addr} | {r.faulting_module or '-'} | {r.monkey_actions} |")
    lines.append("")

    # Detailed bug entries
    bugs = crashes + hangs
    if bugs:
        lines.append("## Bugs found")
        lines.append("")
        for i, r in enumerate(bugs, 1):
            kind = "Crash" if r.outcome == "crash" else "Hang (no log progress at timeout)"
            lines.append(f"### Bug {i}: {kind} — run {r.index}")
            lines.append("")
            lines.append(f"- **Reproduction:** run `python tools/headless_stress_test.py "
                         f"--runs 1 --duration {int(r.duration)+30}`; the failure "
                         f"surfaced after ~{r.duration:.0f}s of monkey input.")
            lines.append(f"- **Exit code:** `{r.classify_exit()}`")
            if r.exception_code is not None:
                name = NT_STATUS_MAP.get(r.exception_code, "UNKNOWN NT STATUS")
                lines.append(f"- **Exception:** {name} (`0x{r.exception_code:08X}`) "
                             f"at address `0x{r.exception_address:016X}`")
            if r.faulting_module:
                lines.append(f"- **Faulting module:** `{r.faulting_module}`")
            if r.minidump_path:
                md_info = _parse_minidump(r.minidump_path)
                if md_info.get("faulting_module") and not r.faulting_module:
                    r.faulting_module = md_info["faulting_module"]
                    lines.append(f"- **Faulting module (from minidump):** `{r.faulting_module}`")
                if md_info.get("thread_count") is not None:
                    lines.append(f"- **Thread count at crash:** {md_info['thread_count']}")
                lines.append(f"- **Minidump:** `{r.minidump_path}` "
                             f"(open with WinDbx/cdb: `cdb -z {r.minidump_path}`)")
                if md_info.get("error"):
                    lines.append(f"- **Minidump parse note:** {md_info['error']}")
            lines.append(f"- **Run log:** `{r.log_path}`")
            if r.signatures:
                lines.append("- **Matching log signatures:**")
                for s in r.signatures[:12]:
                    lines.append(f"    - `{s}`")
            if r.last_log_lines:
                lines.append("- **Last 60 log lines before termination:**")
                lines.append("  ```")
                for l in r.last_log_lines:
                    lines.append(f"  {l}")
                lines.append("  ```")
            lines.append("")
            lines.append("**Recommended fix / next step:**")
            lines.append("")
            if r.outcome == "crash" and r.exception_code == 0xC0000005:
                lines.append("- Access violation. Cross-reference the faulting address "
                             "with the generated function map in "
                             "`generated/default/dantes_inferno_init.h` (the `sub_<addr>` "
                             "table) to identify the guest function. If the address is "
                             "inside `dantes_inferno.exe`, check the corresponding "
                             "`generated/default/sub_<addr>.cpp` for a missed branch "
                             "target or an unimplemented intrinsic; add a "
                             "`[[mid_asm_hooks]]` entry or a function override in the "
                             "manifest if needed. If inside `rexgpu-xenos.dll`, inspect "
                             "the D3D12 command-processor path (see "
                             "`docs/vp6_fmv_corruption_fix.md` for a prior example of a "
                             "VMX/EDRAM bug in the same area).")
            elif r.outcome == "crash" and r.exception_code == 0xC00000FD:
                lines.append("- Stack overflow. Likely an unbounded guest recursion in "
                             "the generated code (a function boundary misdetected by "
                             "codegen, or a missing `[[switch_tables]]` hint causing a "
                             "fall-through loop). Re-run codegen with "
                             "`--log_level=trace` and inspect the failing `sub_<addr>`.")
            elif r.outcome == "hang":
                lines.append("- Hang / no progress within the watchdog window. Could be "
                             "a guest thread spinning on a lock the host never releases, "
                             "or an XAM UI dialog that `--headless` did not bypass. "
                             "Inspect the tail of the run log for the last kernel/GPU "
                             "operation and check `xeXamDispatchHeadless` coverage in "
                             "`thirdparty/rexglue-sdk/src/kernel/xam/xam_ui.cpp`.")
            else:
                lines.append("- Inspect the run log tail and the minidump exception "
                             "record to localize the failure, then map the faulting "
                             "address to a `sub_<addr>` in the generated sources.")
            lines.append("")
    else:
        lines.append("## Bugs found")
        lines.append("")
        lines.append("**No crashes or true hangs were detected across the configured runs.**")
        lines.append("")
        if running:
            lines.append(f"{len(running)} run(s) reached the watchdog timeout while still "
                         "rendering frames (the game's main loop does not self-terminate, so "
                         "this is expected and **not** a hang):")
            lines.append("")
            for r in running:
                lines.append(f"- Run {r.index}: {r.duration:.1f}s, "
                             f"{r.monkey_actions} monkey actions, exit forced by watchdog. "
                             f"Last log activity was within a few seconds of termination.")
            lines.append("")
        lines.append("This is a positive signal but not a proof of correctness: the "
                     "monkey input is randomized and time-bounded, and scene/level warp "
                     "iteration (Option B) was not exercised. Re-run with a longer "
                     "`--duration` and more `--runs` for broader coverage. If any run "
                     "produced `REXLOG_ERROR` / `XFAILED` signatures, they are listed "
                     "below as soft findings.")
        lines.append("")

    # Soft findings: error signatures from clean runs
    soft = [r for r in results if r.outcome in ("clean_exit", "nonzero_exit") and r.signatures]
    if soft:
        lines.append("## Soft findings (error signatures on non-crashing runs)")
        lines.append("")
        for r in soft:
            lines.append(f"### Run {r.index} — {r.outcome} (exit 0x{(r.exit_code or 0):08X})")
            lines.append("")
            for s in r.signatures[:12]:
                lines.append(f"- `{s}`")
            lines.append("")

    lines.append("## Tooling notes & limitations")
    lines.append("")
    lines.append("- **No `--turbo` / `--framerate 0` / `--no-render` flag exists** in "
                 "ReXGlue v0.10.0. `--no-vsync` is the only available frame-rate unlock "
                 "(it sets the guest vblank worker to a 1 ms interval). A true "
                 "headless/no-render mode would require an SDK change to skip window "
                 "creation in `ReXApp::SetupPresentation` and run the graphics system on "
                 "the offscreen provider path.")
    lines.append("- **No PDB is produced** for the release build, so minidump stack "
                 "frames cannot be symbolicated in-process. The harness records the "
                 "exception code, faulting address, and faulting module; for full "
                 "symbolic stacks, rebuild with `-DCMAKE_BUILD_TYPE=RelWithDebInfo` (or "
                 "enable `generate_exception_handlers` in the manifest) and open the "
                 "`.dmp` with `cdb -z <dump>`.")
    lines.append("- **xvfb is not applicable** on Windows; the SDL3 windowing layer "
                 "always creates a window. The harness uses a 320x180 window and posts "
                 "input in the background via `PostMessageW` so the test does not "
                 "hijack the foreground.")
    lines.append("")

    md.write_text("\n".join(lines), encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _default_exe(project_root: Path) -> Path:
    return project_root / "out" / "build" / "win-amd64-release" / "dantes_inferno.exe"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Headless stress test for the ReXGlue Dante's Inferno port")
    ap.add_argument("--exe", default=None, help="Path to dantes_inferno.exe (default: auto-detect)")
    ap.add_argument("--game-root", default="game", help="Game data root (default: game)")
    ap.add_argument("--runs", type=int, default=2, help="Number of runs (default: 2)")
    ap.add_argument("--duration", type=float, default=60.0, help="Per-run timeout in seconds (default: 60)")
    ap.add_argument("--out-dir", default="test", help="Output directory (default: test)")
    ap.add_argument("--no-monkey", action="store_true", help="Disable monkey input injection")
    ap.add_argument("--input-interval-ms", type=int, default=250, help="Monkey input interval (default: 250ms)")
    ap.add_argument("--seed", type=int, default=1337, help="RNG seed (default: 1337)")
    args = ap.parse_args(argv)

    project_root = Path.cwd()
    exe = Path(args.exe) if args.exe else _default_exe(project_root)
    if not exe.exists():
        print(f"ERROR: exe not found: {exe}", file=sys.stderr)
        return 2
    if not (project_root / args.game_root).is_dir():
        print(f"ERROR: game root not found: {project_root / args.game_root}", file=sys.stderr)
        return 2

    out_dir = project_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "minidumps").mkdir(parents=True, exist_ok=True)
    harness_log = out_dir / "headless_test_run.log"

    log_lines: list[str] = []

    def log(msg: str):
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        line = f"{ts} {msg}"
        print(line, flush=True)
        log_lines.append(line)

    log(f"Headless stress test: exe={exe} runs={args.runs} duration={args.duration}s "
        f"monkey={'off' if args.no_monkey else 'on'} out={out_dir}")

    results: list[RunResult] = []
    for i in range(args.runs):
        r = run_one(i, exe, args.game_root, out_dir, args.duration,
                    monkey=not args.no_monkey, input_interval_ms=args.input_interval_ms,
                    rng_seed=args.seed, log=log)
        results.append(r)
        # Brief pause between runs to let OS release the GPU/DLL handles.
        time.sleep(2.0)

    harness_log.write_text("\n".join(log_lines), encoding="utf-8")
    report = write_report(results, out_dir, harness_log)
    log(f"Report written: {report}")

    # Exit non-zero if any crash/hang, so CI can pick it up.
    if any(r.outcome in ("crash", "hang", "launch_failed") for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
