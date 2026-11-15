"""S70 P4 (engineer D5): the keeper's catch-up list is DERIVED from the cadence table.

`task_receipts.TaskSpec.catchup_safe` (default False) + a declared cadence -> `catchup_tasks()`
-> `task_keeper.CATCHUP_TASKS`. The ten names the list held while it was hard-coded stay in it.
"""
from __future__ import annotations

from backend import config as C
from backend.services import task_receipts as TR
from scripts import task_keeper as K

#: The hard-coded list as it stood on main 84871296 (pinned: behaviour for these is unchanged).
OLD_TEN = ("AegisDailyPass", "AegisFleetDailyCheck", "AegisNNLabNightly", "AegisAnalystPanelDaily",
           "AegisHypLabNightly", "AegisContestRehearsal", "AegisDataCatalog", "AegisBrainRefresh",
           "AegisAnalystPull", "AegisPublicFlow")
#: Added S70: idempotent, no order path, a daily or 2-hourly declared cadence.
ADDED = ("AegisForwardCalendar", "AegisOwnerCallsRecord", "AegisDiscoveryAutopsy", "AegisRollingCohorts")
#: Never caught up: live orders, a sim session, messages, its own window, or the keeper itself.
NEVER = ("AegisFleetManagerOpen", "AegisFleetManagerPreclose", "AegisFleetProtectSweep", "AegisSimOwner",
         "AegisTelegramAgent", "AegisAlerts", "AegisIIF1NightLauncher", "AegisCatchUp",
         "AegisPublicAssetsWeekly", "AegisStraddleForward", "AegisNewsOverlayBook", "AegisLLMSelectorBook")


def test_the_old_ten_are_still_caught_up():
    assert set(OLD_TEN) <= set(K.CATCHUP_TASKS)


def test_the_list_is_the_derivation_not_a_copy():
    assert K.CATCHUP_TASKS == TR.catchup_tasks()
    assert set(K.CATCHUP_TASKS) == set(OLD_TEN) | set(ADDED)
    assert len(K.CATCHUP_TASKS) == len(set(K.CATCHUP_TASKS))


def test_no_order_path_or_windowed_task_is_caught_up():
    assert not set(NEVER) & set(K.CATCHUP_TASKS)
    assert not any("FleetManager" in n for n in K.CATCHUP_TASKS)
    # every task the repoint planner keeps attended stays out, except the daily pass (no
    # orders; caught up since 2026-10-02, kept identical) -- its repoint is attended because
    # of the funnel question (OD-i), not because of an order path
    attended = set(C.RUNTIME_REPOINT_ATTENDED_TASKS) - {"AegisDailyPass"}
    assert not attended & set(K.CATCHUP_TASKS)


def test_every_caught_up_task_declares_a_cadence_and_is_not_retired():
    for n in K.CATCHUP_TASKS:
        assert TR.declared_cadence_h(n) is not None, n
        assert not TR.TASK_RECEIPT[n].retired, n


def test_the_derivation_needs_the_flag_and_a_cadence():
    r = TR.r_retired
    table = {"AegisFlagged": TR.TaskSpec(r, "x", catchup_safe=True, cadence_h=24.0),
             "AegisDefault": TR.TaskSpec(r, "x", cadence_h=24.0),
             "AegisNoCadenceAnywhere": TR.TaskSpec(r, "x", catchup_safe=True),
             "AegisRetired": TR.TaskSpec(r, "x", catchup_safe=True, cadence_h=24.0, retired=True),
             "AegisAnalystPull": TR.TaskSpec(r, "x", catchup_safe=True)}      # cadence from config
    assert TR.catchup_tasks(table) == ("AegisFlagged", "AegisAnalystPull")
    assert TR.TaskSpec(r, "x").catchup_safe is False


def test_the_scheduler_read_asks_for_every_derived_name():
    assert K.read_tasks.__defaults__[0] == K.CATCHUP_TASKS
