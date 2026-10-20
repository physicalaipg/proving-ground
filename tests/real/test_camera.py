"""相机采集口径与设备选择的离线自检：不开相机，不调 system_profiler。"""
import subprocess

import numpy as np
import pytest

from real.camera import Camera, CameraConfig, MF200, center_crop, find_camera

DEVICES = [
    {"_name": "iPhone Camera", "spcamera_model-id": "iPhone15,4", "spcamera_unique-id": "1B17"},
    {"_name": "FaceTime HD Camera", "spcamera_model-id": "FaceTime HD Camera", "spcamera_unique-id": "3F45"},
    {"_name": "USB 2.0 Camera", "spcamera_model-id": "UVC Camera VendorID_3141 ProductID_25771",
     "spcamera_unique-id": "0x14210000c45a4ab"},
]


def banded_720p():
    """BGR 帧：左右各 160 列是蓝色，居中 960 列是红色。"""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:, :, 2] = 200
    frame[:, :160] = frame[:, 1120:] = (255, 0, 0)
    return frame


class FakeCapture:
    def __init__(self, frame, refuse=()):
        self.frame, self.refuse, self.sets = frame, refuse, []

    def isOpened(self):
        return True

    def set(self, prop, value):
        self.sets.append((prop, value))
        return prop not in self.refuse

    def read(self):
        return True, self.frame

    def release(self):
        pass


def test_center_crop_keeps_the_middle():
    wide = center_crop(banded_720p(), 640, 480)
    assert wide.shape == (720, 960, 3) and not wide[:, :, 0].any() and (wide[:, :, 2] == 200).all()
    tall = center_crop(np.arange(10 * 4 * 3, dtype=np.uint8).reshape(10, 4, 3), 4, 3)
    assert tall.shape == (3, 4, 3) and tall[0, 0, 0] == 3 * 4 * 3


def test_capture_720p_crops_then_shrinks(monkeypatch):
    cv2 = pytest.importorskip("cv2")
    fake = FakeCapture(banded_720p())
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: fake)
    camera = Camera(CameraConfig(**MF200))
    assert fake.sets == [(cv2.CAP_PROP_FRAME_WIDTH, 1280), (cv2.CAP_PROP_FRAME_HEIGHT, 720)]
    frame = camera.read()
    assert frame.shape == (480, 640, 3) and frame.dtype == np.uint8
    assert (frame[:, :, 0] == 200).all() and not frame[:, :, 2].any()
    fake.frame = np.zeros((480, 640, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        camera.read()


def test_auto_exposure_is_the_default_and_calls_nothing(monkeypatch):
    cv2 = pytest.importorskip("cv2")
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: FakeCapture(banded_720p()))
    calls = []
    camera = Camera(CameraConfig(**MF200), run=lambda *args, **kwargs: calls.append(args))
    assert camera.lock == [] and calls == []


def test_lock_is_set_once_through_uvc_util(monkeypatch):
    cv2 = pytest.importorskip("cv2")
    fake = FakeCapture(banded_720p())
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: fake)
    monkeypatch.setattr("real.camera.list_cameras", lambda: DEVICES)
    calls = []
    camera = Camera(CameraConfig(**MF200, exposure=156, wb_temperature=4600), device="0c45:64ab",
                    run=lambda command, **kwargs: calls.append(command))
    assert calls == [["uvc-util", "-V", "0x0c45:0x64ab", "-s", "auto-exposure-mode=1", "-s", "exposure-time-abs=156",
                      "-s", "auto-white-balance-temp=0", "-s", "white-balance-temp=4600"]]
    assert camera.lock == [("auto-exposure-mode", 1), ("exposure-time-abs", 156),
                           ("auto-white-balance-temp", 0), ("white-balance-temp", 4600)]
    assert fake.sets == [(cv2.CAP_PROP_FRAME_WIDTH, 1280), (cv2.CAP_PROP_FRAME_HEIGHT, 720)]  # 不经 OpenCV 设曝光
    camera.read()
    assert len(calls) == 1


def test_configured_lock_that_cannot_be_set_fails_closed(monkeypatch):
    cv2 = pytest.importorskip("cv2")
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: FakeCapture(banded_720p()))
    monkeypatch.setattr("real.camera.list_cameras", lambda: DEVICES)

    def missing(command, **kwargs):
        raise FileNotFoundError(command[0])

    def refused(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    for run in (missing, refused):
        with pytest.raises(OSError, match="clear both values"):
            Camera(CameraConfig(**MF200, exposure=156), device="USB 2.0", run=run)
    with pytest.raises(OSError, match="product string or VID:PID"):     # 按编号选的相机无从指给 uvc-util
        Camera(CameraConfig(**MF200, wb_temperature=4600), index=0, run=refused)


def test_find_camera_by_product_string_or_ids():
    assert find_camera("usb 2.0", DEVICES) == 2
    assert find_camera("0c45:64ab", DEVICES) == 2
    assert find_camera("FaceTime", DEVICES) == 1
    for selector in ("camera", "0c45:64ac", "MF-200"):
        with pytest.raises(OSError):
            find_camera(selector, DEVICES)


def test_uvc_target_is_0x_prefixed_hex():
    from real.camera import MF200_VID_PID, uvc_target
    assert uvc_target("0C45:636B") == "0x0c45:0x636b" and uvc_target(MF200_VID_PID) == "0x0c45:0x636b"
