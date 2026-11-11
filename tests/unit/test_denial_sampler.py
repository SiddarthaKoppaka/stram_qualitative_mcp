from __future__ import annotations

from stram_qualitative_mcp.http_boundary import DenialSampler


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_first_denials_of_a_window_are_audited_and_the_rest_counted() -> None:
    clock = _Clock()
    sampler = DenialSampler(per_window=3, window_seconds=60.0, clock=clock)

    admitted = [sampler.admit() for _ in range(5)]

    assert admitted == [(True, 0), (True, 0), (True, 0), (False, 0), (False, 0)]


def test_the_count_is_handed_back_once_when_the_next_window_starts() -> None:
    clock = _Clock()
    sampler = DenialSampler(per_window=1, window_seconds=60.0, clock=clock)
    for _ in range(4):
        sampler.admit()

    clock.now += 60.0
    first_of_next = sampler.admit()
    second_of_next = sampler.admit()

    assert first_of_next == (True, 3)
    assert second_of_next == (False, 0)
