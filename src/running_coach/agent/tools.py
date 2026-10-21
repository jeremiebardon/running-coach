"""Agent tools = the application's use cases, exposed to the LLM.

Design rules (they matter more than the prompt):
 - Each tool does ONE job a coach would recognise, with a description that
   says WHEN to use it — that's what drives tool selection.
 - Tools return small, pre-digested JSON (formatted times, paces) instead of
   raw API payloads: fewer tokens, less room for the model to mis-read data.
 - All arithmetic lives in the domain; the model only explains.
 - Errors are returned as {"error": ...} values, not raised, so the model can
   recover ("I couldn't find a run today") instead of the loop crashing.
"""

from dataclasses import asdict
from typing import Annotated, Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from running_coach.data.base import Clock, TrainingData
from running_coach.domain.models import DateRange, is_run
from running_coach.domain.pacing import build_pacing_plan as plan_pacing
from running_coach.domain.predictor import predict_race
from running_coach.domain.time import add_days, format_pace, parse_duration, resolve_distance_m
from running_coach.domain.training import (
    best_efforts,
    describe_performance,
    fitness_snapshot,
    summarise_activity,
    training_context,
    weekly_volume,
)

type Distance = Annotated[
    Literal["5k", "10k", "half", "marathon"] | Annotated[float, Field(gt=0, description="distance in km")],
    Field(description='Race distance: "5k" | "10k" | "half" | "marathon" or a number of km'),
]
type Duration = Annotated[
    str, Field(pattern=r"^\d{1,2}(:\d{2}){1,2}$", description='Duration as "h:mm:ss" or "mm:ss", e.g. "2:55:00"')
]
type IsoDateStr = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class NoArgs(BaseModel):
    pass


class RecentActivitiesArgs(BaseModel):
    days: int = Field(14, ge=1, le=90, description="How many days back to look")
    runs_only: bool = True


class ActivityDetailsArgs(BaseModel):
    activity_id: str | None = None
    date: IsoDateStr | None = Field(None, description="Local date of the run, e.g. today's date")


class FitnessTrendArgs(BaseModel):
    days: int = Field(28, ge=3, le=120)


class TrainingVolumeArgs(BaseModel):
    weeks: int = Field(8, ge=1, le=26)


class BestEffortsArgs(BaseModel):
    days: int = Field(180, ge=14, le=365)


class PredictRaceArgs(BaseModel):
    distance: Distance
    target_time: Duration | None = None
    race_date: IsoDateStr | None = None


class PacingPlanArgs(BaseModel):
    distance: Distance
    target_time: Duration
    strategy: Literal["even", "negative"] = "even"
    split_every_km: float = Field(5, ge=1, le=10)


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def make_tools(data: TrainingData, clock: Clock) -> list[BaseTool]:
    def range_back(days: int) -> DateRange:
        return DateRange(add_days(clock.today(), -days), clock.today())

    @tool(args_schema=NoArgs)
    def get_athlete_snapshot() -> dict:
        """Overview of the athlete right now: profile/thresholds, current fitness (CTL), fatigue (ATL), form (TSB) and the last 4 weeks of running volume. Call this first for broad questions like 'how is my training going?'."""
        profile = data.get_athlete_profile()
        wellness = data.list_wellness(range_back(7))
        activities = data.list_activities(range_back(35))
        latest = next((w for w in reversed(wellness) if w.ctl is not None), None)
        snapshot = fitness_snapshot(latest) if latest else None
        pace = profile.threshold_pace_sec_per_km
        return {
            "today": clock.today(),
            "profile": _drop_none(asdict(profile) | {"threshold_pace": format_pace(pace) if pace else None}),
            "fitness": _drop_none(asdict(snapshot)) if snapshot else None,
            "last_4_weeks": [asdict(w) for w in weekly_volume(activities, clock.today(), 4)],
        }

    @tool(args_schema=RecentActivitiesArgs)
    def list_recent_activities(days: int = 14, runs_only: bool = True) -> list[dict]:
        """List recent activities (newest first) with distance, time, pace, HR and load. Use to find a specific run (e.g. 'today', 'last Sunday's long run') before fetching details."""
        activities = data.list_activities(range_back(days))
        chosen = sorted(
            (a for a in activities if not runs_only or is_run(a)), key=lambda a: a.start_date_local, reverse=True
        )
        return [summarise_activity(a, with_intervals=False) for a in chosen]

    @tool(args_schema=ActivityDetailsArgs)
    def get_activity_details(activity_id: str | None = None, date: str | None = None) -> dict:
        """Detailed analysis of ONE activity, including work intervals (paces and HR per rep). Pass either an activity_id or a date (YYYY-MM-DD); with a date, the most recent run that day is used. Use for 'how was my run today?' or reviewing a workout."""
        if not activity_id:
            day = date or clock.today()
            runs = [a for a in data.list_activities(DateRange(day, day)) if is_run(a)]
            if not runs:
                return {"error": f"No run found on {day}."}
            activity_id = max(runs, key=lambda a: a.start_date_local).id
        activity = data.get_activity(activity_id)
        if activity is None:
            return {"error": f"Activity {activity_id} not found."}
        wellness = data.list_wellness(DateRange(add_days(activity.date, -1), activity.date))
        morning = next((w for w in wellness if w.date == activity.date), None)
        return {
            "activity": summarise_activity(activity),
            "context_that_day": _drop_none(
                {"resting_hr": morning.resting_hr, "hrv": morning.hrv, "sleep_hours": morning.sleep_hours}
            )
            if morning
            else None,
        }

    @tool(args_schema=FitnessTrendArgs)
    def get_fitness_trend(days: int = 28) -> dict:
        """Daily fitness (CTL), fatigue (ATL), form (TSB, % and zone), ramp rate, resting HR, HRV and sleep over a period. Use for freshness/recovery/readiness questions ('am I ready for a hard session?', 'am I overtraining?')."""
        series = []
        for w in data.list_wellness(range_back(days)):
            snapshot = fitness_snapshot(w)
            series.append(
                _drop_none(
                    (asdict(snapshot) if snapshot else {"date": w.date})
                    | {"resting_hr": w.resting_hr, "hrv": w.hrv, "sleep_hours": w.sleep_hours}
                )
            )
        # Down-sample long windows to keep the payload small: daily for the last week, weekly before.
        older = series[:-7]
        return {
            "older_weekly": [s for i, s in enumerate(older) if (len(older) - 1 - i) % 7 == 0],
            "last_seven_days": series[-7:],
        }

    @tool(args_schema=TrainingVolumeArgs)
    def get_training_volume(weeks: int = 8) -> dict:
        """Weekly running volume (km, number of runs, longest run, hours) for the last N weeks, current week last."""
        activities = data.list_activities(range_back(weeks * 7 + 7))
        return {
            "weeks": [asdict(w) for w in weekly_volume(activities, clock.today(), weeks)],
            "note": "The last entry is the current, possibly incomplete, week.",
        }

    @tool(args_schema=BestEffortsArgs)
    def get_best_efforts(days: int = 180) -> list[dict] | dict:
        """Best recent whole-activity performances at 5k / 10k / half / marathon distances (races or race-like efforts)."""
        efforts = best_efforts(data.list_activities(range_back(days)))
        if not efforts:
            return {"error": f"No efforts at standard distances in the last {days} days."}
        return [asdict(p) | {"summary": describe_performance(p)} for p in efforts]

    @tool(args_schema=PredictRaceArgs)
    def predict_race_time(distance: str | float, target_time: str | None = None, race_date: str | None = None) -> dict:
        """Predict a race time from recent performances (VDOT, adjusted for training volume and long runs) and, if a target is given, rate its feasibility. ALWAYS use this for 'could I run X in Y?', 'what's my marathon potential?' questions — never estimate times yourself."""
        activities = data.list_activities(range_back(180))
        return predict_race(
            performances=best_efforts(activities),
            target_distance_m=resolve_distance_m(distance),
            context=training_context(activities, clock.today()),
            today=clock.today(),
            target_time_sec=parse_duration(target_time) if target_time else None,
            race_date=race_date,
        )

    @tool(args_schema=PacingPlanArgs)
    def build_pacing_plan(
        distance: str | float, target_time: str, strategy: str = "even", split_every_km: float = 5
    ) -> dict:
        """Build a race pacing plan (splits every N km) for a target time. Use when the athlete asks how to pace a race."""
        return plan_pacing(
            distance_m=resolve_distance_m(distance),
            target_sec=parse_duration(target_time),
            strategy=strategy,  # type: ignore[arg-type]
            split_every_km=split_every_km,
        )

    return [
        get_athlete_snapshot,
        list_recent_activities,
        get_activity_details,
        get_fitness_trend,
        get_training_volume,
        get_best_efforts,
        predict_race_time,
        build_pacing_plan,
    ]
