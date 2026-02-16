"""Tests for cross-camera ReID engine."""

import math
import time
import pytest

from src.analytics.reid_engine import ReIDEngine, ReIDMatch, ReIDTrack


class TestReIDEngine:
    def test_register_new_track(self):
        engine = ReIDEngine()
        track_id = engine.register_feature(
            "edge-001", "person", [1.0, 0.0, 0.0]
        )
        assert track_id is not None
        assert track_id.startswith("track-")

    def test_match_across_devices(self):
        engine = ReIDEngine(similarity_threshold=0.9)
        now = time.time()
        t1 = engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now)
        t2 = engine.register_feature("edge-002", "person", [0.99, 0.01, 0.0], now + 1)
        # Should match to same track
        assert t1 == t2

    def test_no_match_different_class(self):
        engine = ReIDEngine(similarity_threshold=0.9)
        now = time.time()
        t1 = engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now)
        t2 = engine.register_feature("edge-002", "car", [1.0, 0.0, 0.0], now + 1)
        assert t1 != t2

    def test_no_match_low_similarity(self):
        engine = ReIDEngine(similarity_threshold=0.9)
        now = time.time()
        t1 = engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now)
        t2 = engine.register_feature("edge-002", "person", [0.0, 1.0, 0.0], now + 1)
        assert t1 != t2

    def test_no_match_same_device(self):
        engine = ReIDEngine(similarity_threshold=0.9)
        now = time.time()
        t1 = engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now)
        t2 = engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now + 1)
        # Same device should not match
        assert t1 != t2

    def test_find_matches(self):
        engine = ReIDEngine(similarity_threshold=0.8)
        now = time.time()
        engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now)
        engine.register_feature("edge-002", "person", [0.5, 0.5, 0.0], now + 1)

        matches = engine.find_matches(
            [0.95, 0.05, 0.0], class_name="person", exclude_device="edge-003"
        )
        assert len(matches) >= 1
        assert matches[0].similarity > 0.8

    def test_list_tracks_min_sightings(self):
        engine = ReIDEngine(similarity_threshold=0.95)
        now = time.time()
        engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], now)
        engine.register_feature("edge-002", "person", [1.0, 0.001, 0.0], now + 1)

        tracks = engine.list_tracks(min_sightings=2)
        assert len(tracks) >= 1
        assert len(tracks[0].sightings) >= 2

    def test_get_track(self):
        engine = ReIDEngine()
        track_id = engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0])
        track = engine.get_track(track_id)
        assert track is not None
        assert track.class_name == "person"

    def test_cosine_similarity(self):
        sim = ReIDEngine._cosine_similarity([1, 0, 0], [1, 0, 0])
        assert abs(sim - 1.0) < 0.001

        sim = ReIDEngine._cosine_similarity([1, 0, 0], [0, 1, 0])
        assert abs(sim) < 0.001

        sim = ReIDEngine._cosine_similarity([], [])
        assert sim == 0.0

    def test_time_window_expiry(self):
        engine = ReIDEngine(similarity_threshold=0.9, time_window_seconds=10.0)
        old = time.time() - 100
        engine.register_feature("edge-001", "person", [1.0, 0.0, 0.0], old)
        now = time.time()
        t2 = engine.register_feature("edge-002", "person", [1.0, 0.0, 0.0], now)
        # Old entry should be expired, no match
        tracks = engine.list_tracks(min_sightings=2)
        assert len(tracks) == 0
