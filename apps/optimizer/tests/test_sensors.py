"""Tests des mesures système, sans dépendre du matériel présent."""

from collections import namedtuple
import json
from pathlib import Path

from sakura_opt.sensors import BYTES_PER_GB, BYTES_PER_MB, Sampler
from sakura_opt.temps import read_temps


Disk = namedtuple("Disk", "read_bytes write_bytes busy_time")


class FakePsutil:
    """Faux psutil minimal pour tester les compteurs disque."""

    AccessDenied = PermissionError
    NoSuchProcess = ProcessLookupError

    def __init__(self, disk_samples):
        self.disk_samples = iter(disk_samples)

    def disk_io_counters(self, perdisk=False):
        assert perdisk is True
        return next(self.disk_samples)

    @staticmethod
    def disk_partitions(all=False):
        assert all is False
        return []


def make_disk_sampler(samples, times):
    """Construit un échantillonneur réduit aux tests disque."""
    ticks = iter(times)
    return Sampler(
        psutil_module=FakePsutil(samples),
        monotonic=lambda: next(ticks),
        gpu_reader=object(),
    )


def test_premier_echantillon_disque_a_des_debits_nuls():
    sampler = make_disk_sampler(
        [{"PhysicalDrive0": Disk(12 * BYTES_PER_MB, 8 * BYTES_PER_MB, 900)}],
        [10.0],
    )

    disk = sampler._disk()

    assert disk["read_mb_s"] == 0.0
    assert disk["write_mb_s"] == 0.0
    assert disk["per_disk"]["PhysicalDrive0"]["busy_percent"] == 0.0


def test_debits_disque_utilisent_le_temps_reel_ecoule():
    sampler = make_disk_sampler(
        [
            {"PhysicalDrive0": Disk(10 * BYTES_PER_MB, 5 * BYTES_PER_MB, 1_000)},
            {"PhysicalDrive0": Disk(16 * BYTES_PER_MB, 8 * BYTES_PER_MB, 2_000)},
        ],
        [20.0, 22.0],
    )
    sampler._disk()

    disk = sampler._disk()

    assert disk["read_mb_s"] == 3.0
    assert disk["write_mb_s"] == 1.5
    assert disk["per_disk"]["PhysicalDrive0"]["busy_percent"] == 50.0


def test_erreur_capteur_ne_quitte_pas_sample():
    class BrokenPsutil(FakePsutil):
        @staticmethod
        def cpu_percent(*args, **kwargs):
            raise RuntimeError("compteur CPU cassé")

        @staticmethod
        def virtual_memory():
            raise RuntimeError("mémoire cassée")

        @staticmethod
        def swap_memory():
            raise RuntimeError("échange cassé")

        @staticmethod
        def cpu_count(logical=True):
            return 16

        @staticmethod
        def process_iter(attrs):
            return []

    sampler = Sampler(
        psutil_module=BrokenPsutil([{}]),
        gpu_reader=object(),
        temps_reader=lambda: {"cpu": None},
    )

    result = sampler.sample()

    assert result["cpu"] is None
    assert result["errors"]["cpu"] == "compteur CPU cassé"
    assert "time" in result


def test_gpu_additionne_par_moteur_et_prend_le_maximum():
    # deux processus sur le moteur 3D de la vraie carte, plus une carte virtuelle (Parsec) à part
    class FakeGpu:
        @staticmethod
        def read():
            return (
                [
                    ("pid_1_luid_0x0_0xA_phys_0_eng_0_engtype_3D", 35.0),
                    ("pid_2_luid_0x0_0xA_phys_0_eng_0_engtype_3D", 25.0),
                    ("pid_3_luid_0x0_0xA_phys_0_eng_5_engtype_Copy", 20.0),
                    ("pid_4_luid_0x0_0xB_phys_0_eng_0_engtype_3D", 50.0),
                ],
                [("luid_0", 3 * BYTES_PER_GB), ("luid_1", BYTES_PER_GB)],
            )

    sampler = Sampler(gpu_reader=FakeGpu(), vram_total_reader=lambda: 16.0)

    gpu = sampler._gpu()

    assert gpu == {"percent": 60.0, "vram_used_gb": 3.0, "vram_total_gb": 16.0}


def test_temperatures_sans_dll(tmp_path: Path):
    result = read_temps(tmp_path / "LibreHardwareMonitorLib.dll")

    assert result["source"] is None
    assert result["reason"] == "LibreHardwareMonitor n'est pas installé"


def test_echantillon_reel_est_serialisable_en_json():
    sample = Sampler().sample()

    json.dumps(sample)
    assert sample["gpu"] is None or 0.0 <= sample["gpu"]["percent"] <= 100.0
