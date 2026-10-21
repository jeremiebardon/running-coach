import base64

import httpx
import pytest

from running_coach.data.intervals_icu import IntervalsIcu, IntervalsIcuError
from running_coach.domain.models import DateRange


def adapter(handler, **kwargs) -> IntervalsIcu:
    return IntervalsIcu("secret", client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)


def test_uses_basic_auth_with_the_api_key_username_and_maps_activities():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "i123",
                    "name": "Long run",
                    "type": "Run",
                    "start_date_local": "2026-10-11T08:00:00",
                    "distance": 28000,
                    "moving_time": 8200,
                    "average_heartrate": 145,
                    "icu_training_load": 160,
                    "some_unknown_field": {"ignored": True},
                }
            ],
        )

    [a] = adapter(handler).list_activities(DateRange("2026-10-01", "2026-10-17"))

    assert (
        str(requests[0].url) == "https://intervals.icu/api/v1/athlete/0/activities?oldest=2026-10-01&newest=2026-10-17"
    )
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b"API_KEY:secret").decode()
    assert (a.id, a.distance_m, a.moving_time_sec, a.avg_hr, a.training_load) == ("i123", 28000, 8200, 145, 160)


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("running_coach.data.intervals_icu.time.sleep", lambda _: None)
    responses = iter(
        [
            httpx.Response(429, json={}),
            httpx.Response(200, json=[{"id": "2026-10-17", "ctl": 55, "atl": 40, "sleepSecs": 27000}]),
        ]
    )
    calls = []

    def handler(request):
        calls.append(request)
        return next(responses)

    [w] = adapter(handler, max_retries=1).list_wellness(DateRange("2026-10-17", "2026-10-17"))
    assert len(calls) == 2
    assert (w.date, w.ctl, w.atl, w.sleep_hours, w.ramp_rate) == ("2026-10-17", 55, 40, 7.5, None)


def test_returns_none_for_a_missing_activity_and_raises_on_auth_errors():
    assert adapter(lambda r: httpx.Response(404, json={})).get_activity("nope") is None
    with pytest.raises(IntervalsIcuError) as err:
        adapter(lambda r: httpx.Response(401, json={})).get_activity("x")
    assert err.value.status == 401
