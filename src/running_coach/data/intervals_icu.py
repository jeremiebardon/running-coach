import time
from urllib.parse import quote

import httpx
from pydantic import BaseModel, TypeAdapter

from running_coach.data.schemas import (
    RawActivity,
    RawAthlete,
    RawWellness,
    to_activity,
    to_athlete_profile,
    to_wellness,
)
from running_coach.domain.models import Activity, AthleteProfile, DateRange, WellnessDay


class IntervalsIcuError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class IntervalsIcu:
    """Training data from https://intervals.icu/api/v1

    Auth: HTTP Basic, username "API_KEY", password = your key (Settings → Developer).

    Gotcha: activities imported from Strava are NOT returned by the API (Strava's
    terms). Sync Garmin → intervals.icu directly.
    """

    def __init__(
        self,
        api_key: str,
        athlete_id: str = "0",
        *,
        base_url: str = "https://intervals.icu/api/v1",
        timeout_s: float = 15,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self._athlete = f"/athlete/{athlete_id}"
        self._max_retries = max_retries
        self._client = client or httpx.Client()
        self._client.base_url = base_url
        self._client.auth = httpx.BasicAuth("API_KEY", api_key)
        self._client.timeout = httpx.Timeout(timeout_s)
        self._client.headers["Accept"] = "application/json"

    def get_athlete_profile(self) -> AthleteProfile:
        return to_athlete_profile(self._get(self._athlete, RawAthlete))

    def list_activities(self, range: DateRange) -> list[Activity]:
        raws = self._get(f"{self._athlete}/activities", list[RawActivity], oldest=range.oldest, newest=range.newest)
        return [to_activity(r) for r in raws]

    def get_activity(self, id: str) -> Activity | None:
        try:
            return to_activity(self._get(f"/activity/{quote(id, safe='')}", RawActivity, intervals="true"))
        except IntervalsIcuError as e:
            if e.status == 404:
                return None
            raise

    def list_wellness(self, range: DateRange) -> list[WellnessDay]:
        raws = self._get(f"{self._athlete}/wellness", list[RawWellness], oldest=range.oldest, newest=range.newest)
        return [to_wellness(r) for r in raws]

    def _get[T](self, path: str, schema: type[T], **params: str) -> T:
        """GET + retry with exponential backoff on 429/5xx + schema validation."""
        attempt = 0
        while True:
            res = self._client.get(path, params=params)
            if res.is_success:
                if isinstance(schema, type) and issubclass(schema, BaseModel):
                    return schema.model_validate(res.json())
                return TypeAdapter(schema).validate_python(res.json())
            retryable = res.status_code == 429 or res.status_code >= 500
            if not retryable or attempt >= self._max_retries:
                raise IntervalsIcuError(res.status_code, f"intervals.icu {res.status_code} on GET {path}")
            time.sleep(0.5 * 2**attempt)
            attempt += 1
