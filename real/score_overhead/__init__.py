"""Offline overhead scoring v0 (internal work order D; ruling 2026-10-05-05).

markers.py  ArUco sheet (car top id 0, arena corners ids 1–4) → PDF for printing.
track.py    overhead video → per-frame car pose in arena metres (homography from the four corner markers or
            the registration clicks) → track.csv.
score.py    track.csv (+ optional episode log for step alignment) → checkpoint arrivals (reach radius), contact
            events (car footprint vs dilated obstacle footprints and the boundary), path length; same summary
            keys as harness.scoring.ScoreState (the single scoring source), plus source="overhead".
synth.py    synthetic overhead video for the self-test; a hand-pushed real video is the acceptance (令文 D).
"""
