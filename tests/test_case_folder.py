"""Offline tests for the case-folder path (builder/case): source reading, contract parsing, workflow emission.
The fixture is a made-up clinic, so nothing here depends on a particular bank."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from builder.case import emit  # noqa: E402
from builder.case import sources as S  # noqa: E402

CONTRACT = """# Clinic services

Every service is `POST`, JSON in, JSON out. Base address:

```
https://api.clinic.example/desk/v2/
```

| # | Service | Called with | Gives back |
|---|---|---|---|
| 1 | `visits.list` | patient id | the patient's visits |
| 2 | `visit.move` | visit id + day | moves the visit |

### 1 `visits.list`

Request:

```json
{ "data": { "patientId": "p1", "channel": "Voice" }, "meta": { "caller": "<caller's number>" } }
```

Returns the visits.

### 2 `visit.move`

Request:

```json
{ "data": { "visitId": "v-1", "day": 3 }, "meta": { "caller": "<caller's number>" } }
```
"""


def make_case(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "BRIEF.md").write_text("Every call gives `patientId` and `now`.")
    (tmp_path / "docs" / "2026-01-05-contract.md").write_text(CONTRACT)
    (tmp_path / "docs" / "2026-01-02-rules.md").write_text("old rules")
    (tmp_path / "docs" / "2026-02-02-rules.md").write_text("new rules")
    (tmp_path / "data.json").write_text("{}")
    return tmp_path


def spec():
    return {"sections": {"start": ["Greet."], "reading": ["Read the visits."], "actions": ["Move a visit after a yes."],
                         "failures": ["On failure transfer."], "security": ["Never read ids."]},
            "endings": [{"destination": "Front desk", "when": "a service failed", "last_sentence": "I am putting you through."},
                        {"destination": "front desk", "when": "caller asks for a person", "last_sentence": "One moment."},
                        {"destination": "hang up", "when": "nothing else", "last_sentence": ""}],
            "wiring": {"language": "English", "start_service": "visits.list",
                       "call_variables": [{"name": "patientId", "meaning": "patient", "example": "p9"},
                                          {"name": "now", "meaning": "time of call", "example": "2026-03-01T10:00:00+03:00"}],
                       "services": {"visits.list": {"changes_something": False}, "visit.move": {"changes_something": True}},
                       "fields": {"visits.list": {"patientId": {"source": "call_variable", "value": "patientId"},
                                                  "channel": {"source": "constant", "value": "Voice"}},
                                  "visit.move": {"visitId": {"source": "conversation", "note": "copied from visits.list"},
                                                 "day": {"source": "conversation", "note": "the day the caller chose"}}}}}


def test_sources_keep_newest_edition_and_order(tmp_path):
    docs, skipped = S.read_sources(make_case(tmp_path))
    paths = [d["path"] for d in docs]
    assert "docs/2026-01-02-rules.md" not in paths and "docs/2026-02-02-rules.md" in paths
    assert paths[-1] == "BRIEF.md"  # undated last
    assert paths.index("docs/2026-01-05-contract.md") < paths.index("docs/2026-02-02-rules.md")
    assert any(s["file"] == "data.json" for s in skipped)


def test_contract_is_parsed(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    c = S.find_contract(docs)
    assert c["base_path"] == "/desk/v2/" and c["method"] == "POST"
    assert [s["name"] for s in c["services"]] == ["visits.list", "visit.move"]
    assert c["services"][1]["request_example"]["data"] == {"visitId": "v-1", "day": 3}
    assert "patient id" in c["services"][0]["summary"]


def test_workflow_shape(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    c = S.find_contract(docs)
    wf, summary = emit.build(spec(), c, "https://mock.example/")
    assert emit.lint(wf) == []
    assert wf["initial_node"] == "assistant" and summary["start_service"] == "visits.list" and summary["now_variable"] == "now"
    tools = wf["nodes"]["assistant"]["tools"]
    assert [t["function"]["name"] for t in tools] == ["visits_list", "visit_move"]
    assert "CALL the tool visits_list" in wf["nodes"]["assistant"]["task_message"]
    start = tools[0]["function"]["parameters"]["properties"]
    assert start["url"]["default"] == "https://mock.example/desk/v2/visits.list"
    data = start["body"]["properties"]["data"]["properties"]
    assert data["patientId"]["default"] == "{{patientId}}" and data["channel"]["default"] == "Voice"
    assert start["body"]["properties"]["meta"]["properties"]["caller"]["default"] == ""  # placeholder is not a value
    move = tools[1]["function"]["parameters"]["properties"]["body"]["properties"]["data"]
    assert move["required"] == ["visitId", "day"] and move["properties"]["day"]["type"] == "integer"
    ends = {k: n for k, n in wf["nodes"].items() if n["node_type"] == "end_call"}
    assert sorted(ends) == ["end_front_desk_1", "end_front_desk_2", "end_hang_up_1"]
    assert ends["end_front_desk_2"]["terminal"]["function"]["name"] == "front_desk"
    assert ends["end_hang_up_1"]["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"] == "none"
    assert all(t.get("is_tool_call") for t in wf["nodes"]["assistant"]["transitions"])
    for t in tools:
        compile(t["pre_process_code"], "<pre>", "exec")
        compile(t["post_process_code"], "<post>", "exec")


def test_start_service_needs_only_known_values(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    c = S.find_contract(docs)
    s = spec()
    s["wiring"]["fields"]["visits.list"]["patientId"] = {"source": "conversation", "note": "asked"}
    wf, summary = emit.build(s, c, "https://mock.example")
    assert summary["start_service"] == "" and "START OF THIS CALL" not in wf["nodes"]["assistant"]["task_message"]
    assert len(wf["nodes"]["assistant"]["tools"]) == 2


def test_post_hook_adds_date_facts():
    hook = emit._const("NOW_VAR", "now") + emit.POST_HOOK
    result = {"status": "success", "header": {"x": 1}, "data": {"data": {"due": "15.10.2026", "cut": "05.10.2026", "today": "12.10.2026"},
                                                                 "result": {"code": "1", "details": {"guid": "g"}}}}
    exec(hook, {"result": result, "vars": {"now": "2026-10-12T10:30:00+03:00"}})
    notes = result["data"]["assistant_notes"]["dates"]
    assert "header" not in result and "details" not in result["data"]["result"]
    assert "in 3 day(s)" in notes["data.due"] and "already passed" in notes["data.cut"] and notes["data.today"].endswith("is today")


def test_consent_guard_refuses_a_change_in_the_same_turn_as_a_service_result(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    wf, summary = emit.build(spec(), S.find_contract(docs), "https://mock.example")
    assert summary["consent_guard_on"] == ["visit.move"]
    pre = wf["nodes"]["assistant"]["tools"][1]["pre_process_code"]
    v = {"assistant.total_turns": 3, "last_service_turn": "3"}
    try:
        exec(pre, {"vars": v, "config": {}})
        raised = False
    except Exception as e:
        raised = str(e).startswith("NOT ALLOWED YET")
    assert raised
    v = {"assistant.total_turns": 4, "last_service_turn": "3"}
    exec(pre, {"vars": v, "config": {}})  # the caller has spoken since: allowed
    assert v["last_service_turn"] == "4"


def test_call_variable_fields_are_written_from_the_live_call(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    c = S.find_contract(docs)
    s = spec()
    s["wiring"]["fields"]["visit.move"]["visitId"] = {"source": "call_variable", "value": "patientId"}
    wf, summary = emit.build(s, c, "https://mock.example")
    assert "test_variables" not in wf and summary["example_variables"]["patientId"] == "p9"
    pre = wf["nodes"]["assistant"]["tools"][-1]["pre_process_code"]
    config = {"body": {"data": {"visitId": "p9", "day": 3}, "meta": {"caller": ""}}}
    exec(pre, {"vars": {"assistant.total_turns": 2, "patientId": "real-77"}, "config": config})
    assert json.loads(config["body"]) == {"data": {"visitId": "real-77", "day": 3}, "meta": {"caller": ""}}
