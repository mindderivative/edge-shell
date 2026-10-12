import pytest

from services.sysinfo import cpu_percent, parse_cpu_times, parse_meminfo

MEMINFO = "MemTotal:       16000000 kB\nMemFree:         1000000 kB\nMemAvailable:    4000000 kB\n"
STAT_A = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 50 0 50 350 50 0 0 0 0 0\n"
STAT_B = "cpu  200 0 200 1000 100 0 0 0 0 0\ncpu0 100 0 100 500 50 0 0 0 0 0\n"


def test_parse_meminfo_percent_used():
    assert parse_meminfo(MEMINFO) == pytest.approx(75.0)


def test_parse_cpu_times_total_and_idle():
    assert parse_cpu_times(STAT_A) == (1000, 800)  # idle = idle + iowait


def test_cpu_percent_between_samples():
    assert cpu_percent(parse_cpu_times(STAT_A), parse_cpu_times(STAT_B)) == pytest.approx(40.0)


def test_cpu_percent_no_elapsed_time_is_zero():
    sample = parse_cpu_times(STAT_A)
    assert cpu_percent(sample, sample) == 0.0
