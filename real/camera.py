"""USB camera with a lazy OpenCV dependency; injected sources return RGB."""
from dataclasses import dataclass
import json
import re
import subprocess

import numpy as np


@dataclass(frozen=True)
class CameraConfig:
    width: int = 640
    height: int = 480
    hfov_deg: float = 70.0
    height_m: float = 0.15
    forward_offset_m: float = 0.10
    capture_width: int = 0  # 0 captures at the output size, no crop
    capture_height: int = 0
    pitch_deg: float = 0.0
    exposure: int | None = None  # UVC exposure-time-abs, units of 100 us; None leaves exposure on auto (the default)
    wb_temperature: int | None = None  # UVC white-balance-temp, kelvin; None leaves white balance on auto


# MF-200 1080p module, 2.8 mm lens: capture 1280x720, centre-crop to 4:3, shrink to 640x480.
# hfov_deg is computed from the sensor's active area, not measured; height_m and pitch_deg keep their defaults until measured.
# Exposure and white balance stay on auto for the first season; fill both lock values here only after uvc-util sets them on the real camera.
MF200 = {"capture_width": 1280, "capture_height": 720, "hfov_deg": 75.0}
MF200_VID_PID = "0c45:636b"  # read on the Mac 2026-10-06 (system_profiler VendorID_3141 ProductID_25451; uvc-util lists "USB 2.0 Camera")
UVC_UTIL = "uvc-util"


def center_crop(frame, width, height):
    """Largest centred window with the output aspect ratio."""
    rows, cols = frame.shape[:2]
    if cols * height >= rows * width:
        keep = rows * width // height
        left = (cols - keep) // 2
        return frame[:, left:left + keep]
    keep = cols * height // width
    top = (rows - keep) // 2
    return frame[top:top + keep]


def crop_resize(frame, width, height):
    cropped = center_crop(frame, width, height)
    if cropped.shape[:2] == (height, width):
        return cropped
    import cv2
    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_AREA)


def list_cameras():
    """Cameras in the order OpenCV's AVFoundation backend indexes them: sorted by unique id. macOS only."""
    listing = subprocess.run(["system_profiler", "SPCameraDataType", "-json"], capture_output=True, text=True,
                             check=True).stdout
    return sorted(json.loads(listing)["SPCameraDataType"], key=lambda device: device["spcamera_unique-id"])


def find_camera(selector, devices=None):
    """Index of the one camera whose name contains the product string or whose USB ids equal VID:PID in hex."""
    devices = list_cameras() if devices is None else devices
    ids = re.fullmatch(r"([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", selector)
    if ids:
        want = (int(ids[1], 16), int(ids[2], 16))
        found = [re.search(r"VendorID_(\d+) ProductID_(\d+)", device.get("spcamera_model-id", "")) for device in devices]
        hits = [i for i, match in enumerate(found) if match and (int(match[1]), int(match[2])) == want]
    else:
        hits = [i for i, device in enumerate(devices) if selector.lower() in device.get("_name", "").lower()]
    if len(hits) != 1:
        raise OSError("camera %r matches %d of %s" % (selector, len(hits), [device.get("_name") for device in devices]))
    return hits[0]


def uvc_settings(config):
    """uvc-util controls for the configured lock, in the order they are set; empty when both stay on auto."""
    settings = []
    if config.exposure is not None:
        settings += [("auto-exposure-mode", 1), ("exposure-time-abs", int(config.exposure))]  # 1 is UVC manual mode
    if config.wb_temperature is not None:
        settings += [("auto-white-balance-temp", 0), ("white-balance-temp", int(config.wb_temperature))]
    return settings


def uvc_target(vid_pid):
    """uvc-util -V wants 0x-prefixed hex ("0c45:636b" alone is read as a decimal and rejected; checked on the MF-200 2026-10-06)."""
    vid, pid = vid_pid.split(":")
    return "0x%s:0x%s" % (vid.lower(), pid.lower())


def apply_uvc_lock(config, device, run=subprocess.run):
    """Set the lock once through uvc-util, a UVC control transfer outside OpenCV. Returns what was set."""
    settings = uvc_settings(config)
    if not settings:
        return settings
    if device is None:
        raise OSError("exposure or white balance lock needs the camera picked by product string or VID:PID")
    target = ["-V", uvc_target(device)] if re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", device) else ["-N", device]
    command = [UVC_UTIL, *target] + [part for name, value in settings for part in ("-s", "%s=%d" % (name, value))]
    try:
        run(command, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OSError("uvc-util could not set the exposure or white balance lock; clear both values to run on auto: %s"
                      % exc) from exc
    return settings


class Camera:
    def __init__(self, config=CameraConfig(), *, frame_source=None, index=0, device=None, run=subprocess.run):
        self.config, self.frame_source = config, frame_source
        self.capture = None
        self.lock = []  # uvc-util controls actually set; empty means auto exposure and auto white balance
        self.capture_size = (config.capture_height or config.height, config.capture_width or config.width)
        if frame_source is None:
            import cv2
            if device is None:
                self.capture = cv2.VideoCapture(index)
            else:
                self.capture = cv2.VideoCapture(find_camera(device), cv2.CAP_AVFOUNDATION)
            if not self.capture.isOpened():
                self.capture.release()
                raise OSError("camera unavailable")
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_size[1])
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_size[0])
            try:
                self.lock = apply_uvc_lock(config, device, run)  # once, before the first frame
            except OSError:
                self.capture.release()
                raise

    def read(self):
        if self.frame_source is not None:
            frame = self.frame_source()
        else:
            ok, bgr = self.capture.read()
            if not ok:
                raise OSError("camera frame unavailable")
            if bgr.shape[:2] != self.capture_size:
                raise ValueError("camera must capture the configured size")
            frame = crop_resize(bgr, self.config.width, self.config.height)[:, :, ::-1]
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.shape != (self.config.height, self.config.width, 3):
            raise ValueError("camera must supply configured HxWx3 uint8 RGB")
        return frame.copy()

    def close(self):
        if self.capture is not None:
            self.capture.release()
