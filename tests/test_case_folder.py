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
                       "consent": {"clear_yes": ["Yes", "I confirm"], "not_clear": ["I suppose", "maybe"]},
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
    assert wf["initial_node"] == "boot" and summary["start_service"] == "visits.list" and summary["now_variable"] == "now"
    boot = wf["nodes"]["boot"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    v = {}
    exec(boot, {"vars": v})
    assert sorted(v) == ["mem_visit_move", "mem_visits_list"]
    assert "{{mem_visits_list}}" in wf["nodes"]["assistant"]["task_message"]
    tools = wf["nodes"]["assistant"]["tools"]
    assert [t["function"]["name"] for t in tools] == ["visits_list", "visit_move"]
    assert "CALL the tool visits_list" in wf["nodes"]["assistant"]["task_message"]
    assert "v-1" not in json.dumps(tools)  # no sample value from the contract reaches a tool description
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
    hook = emit._const("NOW_VAR", "now") + emit._const("TOOL", "bal") + emit.POST_HOOK
    result = {"status": "success", "header": {"x": 1}, "data": {"data": {"due": "15.10.2026", "cut": "05.10.2026", "today": "12.10.2026", "min": 34.1, "debt": 85.2, "round": 12000.0},
                                                                 "result": {"code": "1", "details": {"guid": "g"}}}}
    v = {"now": "2026-10-12T10:30:00+03:00", "bal_args.cardNumber": "54**12"}
    exec(hook, {"result": result, "vars": v})
    notes = result["data"]["assistant_notes"]["dates"]
    assert v["mem_bal"].startswith("answered for cardNumber=54**12:") and "data.due = 15.10.2026 (is in 3 day(s), not reached yet)" in v["mem_bal"]
    assert "result" not in v["mem_bal"].split(":", 1)[1] and "{{" not in v["mem_bal"]
    amounts = result["data"]["assistant_notes"]["amounts_with_decimals"]
    assert amounts["data.min"].startswith("34.10 exactly: whole part 34, then 10 hundredths") and "data.round" not in amounts
    assert "data.min = 34.1 (34.10 exactly" in v["mem_bal"]
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


def test_consent_guard_wants_a_clear_yes(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    wf, summary = emit.build(spec(), S.find_contract(docs), "https://mock.example")
    assert summary["clear_yes"] == ["yes", "i confirm"] and summary["not_clear"] == ["i suppose", "maybe"]
    pre = wf["nodes"]["assistant"]["tools"][1]["pre_process_code"]
    read_only = wf["nodes"]["assistant"]["tools"][0]["pre_process_code"]

    def allowed(code, said):
        v = {"assistant.total_turns": 5, "last_service_turn": "4",
             "system.conversation": [{"role": "assistant", "content": "Do you confirm?"}, {"role": "user", "content": said}]}
        try:
            exec(code, {"vars": v, "config": {}})
            return True
        except Exception as e:
            assert str(e).startswith("NOT ALLOWED YET")
            return False

    assert allowed(pre, "Yes.") and allowed(pre, "YES, I confirm!")
    assert not allowed(pre, "Fine, I suppose") and not allowed(pre, "yes maybe") and not allowed(pre, "go on then")
    assert allowed(read_only, "go on then")  # only services that change something are guarded
    v = {"assistant.total_turns": 5, "last_service_turn": "4"}  # no transcript visible: the turn rule alone applies
    exec(pre, {"vars": v, "config": {}})


def test_unknowable_facts_go_to_the_top_of_the_instructions(tmp_path):
    docs, _ = S.read_sources(make_case(tmp_path))
    s = spec()
    s["sections"]["assume"] = ["You cannot know: whether the yearly move is used. So: always offer the move."]
    wf, _ = emit.build(s, S.find_contract(docs), "https://mock.example")
    p = wf["system_prompt"]
    assert "always offer the move" in p and p.index("WHAT NO SERVICE TELLS YOU") < p.index("OFFERS AND ACTIONS")
