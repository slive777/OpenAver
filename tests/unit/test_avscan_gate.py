import threading

from core.avscan.gate import AvscanGate


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_gate_consecutive_calls_only_first_allowed():
    clock = FakeClock(0.0)
    gate = AvscanGate(clock=clock, min_gap=5)
    results = []
    for _ in range(5):
        results.append(gate.try_acquire())
        gate.release()
    assert results[0] == (True, 0)
    for ok, retry_after in results[1:]:
        assert ok is False
        assert isinstance(retry_after, int) and retry_after >= 1
    clock.now = 0.2
    assert gate.try_acquire() == (False, 5)
    clock.now = 5
    assert gate.try_acquire()[0] is True


def test_gate_in_flight_blocks_even_after_gap():
    clock = FakeClock(0.0)
    gate = AvscanGate(clock=clock, min_gap=5)
    assert gate.try_acquire()[0] is True
    clock.now = 100
    ok, retry_after = gate.try_acquire()
    assert ok is False and retry_after >= 1
    gate.release()
    assert gate.try_acquire()[0] is True


def test_gate_concurrent_threads_single_winner():
    gate = AvscanGate(clock=FakeClock(0.0), min_gap=5)
    barrier = threading.Barrier(8)
    wins = []

    def worker():
        barrier.wait()
        wins.append(gate.try_acquire()[0])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1 and len(wins) == 8


def test_gate_penalize_blocks_until_expiry():
    clock = FakeClock(0.0)
    gate = AvscanGate(clock=clock, min_gap=5)
    gate.penalize(10)
    clock.now = 9
    assert gate.try_acquire()[0] is False
    clock.now = 10
    assert gate.try_acquire()[0] is True

    clock2 = FakeClock(0.0)
    gate2 = AvscanGate(clock=clock2, min_gap=5)
    gate2.penalize(1)
    clock2.now = 4
    assert gate2.try_acquire()[0] is False
    clock2.now = 5
    assert gate2.try_acquire()[0] is True
