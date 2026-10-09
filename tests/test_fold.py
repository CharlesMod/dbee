"""One case per fault: a storm of wakes about one service while its case is worked is that case's."""
from dbee.watch import Fold, Wake


def test_wakes_raised_before_a_case_ended_are_that_case_and_a_later_one_is_a_recurrence():
    f = Fold()
    first = Wake("unit_failed", "cron.service", at=100.0)
    assert f.admit(first)
    storm = [Wake("unit_failed", "cron.service", at=100.1), Wake("line", "cron.service: Failed with result 'exit-code'.",
             at=100.2, evidence="cron.service: Failed with result 'exit-code'."), Wake("unit_failed", "cron", at=900.0)]
    f.ended(first, 1000.0)                    # the case took 15 minutes; everything raised meanwhile is folded into it
    assert not any(f.admit(w) for w in storm)
    assert f.admit(Wake("unit_failed", "nginx.service", at=500.0))     # another service is another fault
    assert f.admit(Wake("unit_failed", "cron.service", at=1000.5))     # after the close: it came back, a new case
