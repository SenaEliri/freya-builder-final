// Replays every fixture in the bank's file against a running mock over real HTTP and
// deep-compares status and body. Also runs a handful of negative checks.
// Usage: node scripts/replay.mjs <base-url> [--skip-delay]
import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";

const base = (process.argv[2] ?? "http://localhost:8787").replace(/\/+$/, "");
const skipDelay = process.argv.includes("--skip-delay");
const doc = JSON.parse(readFileSync(new URL("../fixtures/test-customers.json", import.meta.url), "utf8"));

const CALL = { ani: "+905000000000", lang: "tr" };
const PDF = { cardNumber: "540000******1234", currencyType: "TL", statementDate: "05.10.2026", emailAddress: "ornek@freyabank.example" };

function dataFor(service, customerNo, card, week) {
  if (service === "cards.list") return { customerNo, aiFlow: "CardOps" };
  if (service === "contact.email.get") return { customerNo, intAddressInfoType: "E" };
  if (service === "statement.pdf.send") return { customerNo, ...PDF };
  if (service === "cards.balance" || service === "statement.week.get") return { cardNumber: card };
  return { cardNumber: card, newStatementWeek: Number(week), statementDay: 5 };
}

const cases = [];
for (const c of doc.customers) {
  for (const [service, node] of Object.entries(c.services)) {
    if (["cards.list", "contact.email.get", "statement.pdf.send"].includes(service)) cases.push({ service, customerNo: c.customerNo, entry: node });
    else if (["cards.balance", "statement.week.get"].includes(service))
      for (const [card, entry] of Object.entries(node)) cases.push({ service, customerNo: c.customerNo, card, entry });
    else
      for (const [card, weeks] of Object.entries(node))
        for (const [week, entry] of Object.entries(weeks)) cases.push({ service, customerNo: c.customerNo, card, week, entry });
  }
}

async function post(service, data, raw) {
  const started = Date.now();
  const res = await fetch(`${base}/voice/v1/${service}`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json", authorization: "Bearer test" },
    body: raw ?? JSON.stringify({ data, call: CALL }),
    signal: AbortSignal.timeout(60_000),
  });
  const text = await res.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  return { status: res.status, body, ms: Date.now() - started, preview: res.headers.get("x-mock-preview") };
}

let pass = 0;
const failures = [];
const byStatus = {};
const check = (ok, label, detail) => (ok ? pass++ : failures.push(`${label}${detail ? ` :: ${detail}` : ""}`));

console.log(`Replaying ${cases.length} fixtures against ${base}`);
const fast = cases.filter((c) => !c.entry.delaySeconds);
const slow = cases.filter((c) => c.entry.delaySeconds);

const timings = [];
for (let i = 0; i < fast.length; i += 8) {
  await Promise.all(
    fast.slice(i, i + 8).map(async (c) => {
      const label = [c.service, c.customerNo, c.card, c.week].filter(Boolean).join(" ");
      try {
        const r = await post(c.service, dataFor(c.service, c.customerNo, c.card, c.week));
        timings.push(r.ms);
        byStatus[r.status] = (byStatus[r.status] ?? 0) + 1;
        check(r.status === c.entry.http && isDeepStrictEqual(r.body, c.entry.response) && r.preview === null, label, `got ${r.status} ${JSON.stringify(r.body).slice(0, 160)}`);
      } catch (e) {
        check(false, label, String(e));
      }
    }),
  );
}
timings.sort((a, b) => a - b);
console.log(`fixtures (non-delayed): ${fast.length - failures.length}/${fast.length} exact | statuses ${JSON.stringify(byStatus)} | latency ms p50=${timings[timings.length >> 1]} max=${timings.at(-1)}`);

for (const c of slow) {
  const label = `DELAYED ${c.service} ${c.customerNo} ${c.card}`;
  if (skipDelay) { console.log(`${label}: skipped (--skip-delay)`); continue; }
  const r = await post(c.service, dataFor(c.service, c.customerNo, c.card, c.week));
  const ok = r.status === c.entry.http && isDeepStrictEqual(r.body, c.entry.response) && r.ms >= c.entry.delaySeconds * 1000;
  check(ok, label, `status ${r.status} after ${r.ms} ms`);
  console.log(`${label}: status ${r.status}, body ${isDeepStrictEqual(r.body, c.entry.response) ? "exact" : "DIFFERENT"}, took ${r.ms} ms (configured ${c.entry.delaySeconds} s)`);
}

const before = failures.length;
const isErr = (r, http, code) => r.status === http && r.body?.result?.code === code && r.body.result.returnCode === code && r.body.result.guid === r.body.result.details?.guid && !("data" in r.body);
const neg = async (label, service, data, http, code, raw) => {
  const r = await post(service, data, raw);
  check(isErr(r, http, code), `NEG ${label}`, `got ${r.status} ${JSON.stringify(r.body).slice(0, 160)}`);
};
await neg("unknown customer cards.list", "cards.list", { customerNo: "11111111" }, 404, "FB_IVR_CHANNEL_102");
await neg("unknown card cards.balance", "cards.balance", { cardNumber: "540000******0000" }, 404, "FB_IVR_CHANNEL_120");
await neg("unknown card statement.week.get", "statement.week.get", { cardNumber: "540000******0000" }, 404, "FB_IVR_CHANNEL_121");
await neg("unknown customer statement.pdf.send", "statement.pdf.send", { customerNo: "11111111", ...PDF }, 404, "FB_IVR_CHANNEL_107");
await neg("no pdf entry (96125950)", "statement.pdf.send", { customerNo: "96125950", ...PDF }, 404, "FB_IVR_CHANNEL_107");
await neg("unknown customer contact.email.get", "contact.email.get", { customerNo: "11111111", intAddressInfoType: "E" }, 400, "INVALID_ARGUMENTS_ERROR");
await neg("current week decide", "statement.week.decide", { cardNumber: "540000******1110", newStatementWeek: 2, statementDay: 9 }, 400, "INVALID_ARGUMENTS_ERROR");
await neg("current week change", "statement.week.change", { cardNumber: "540000******1110", newStatementWeek: "2", statementDay: 9 }, 400, "INVALID_ARGUMENTS_ERROR");
await neg("empty card number", "cards.balance", { cardNumber: "" }, 400, "INVALID_ARGUMENTS_ERROR");
await neg("malformed JSON", "cards.list", null, 400, "INVALID_ARGUMENTS_ERROR", "{not json");
await neg("balance-style masking", "cards.balance", { cardNumber: "5400********1234" }, 404, "FB_IVR_CHANNEL_120");

const num = await post("cards.list", { customerNo: 92030487 });
check(num.status === 200 && num.body?.data?.validCardsCount === 4, "numeric customerNo");
const wk = await post("statement.week.decide", { cardNumber: "540000******1110", newStatementWeek: "3", statementDay: 9 });
check(wk.status === 200 && wk.body?.data?.statementDate === "16.11.2026", "string week");
const tpl = await post("cards.list", { customerNo: "{{customerNumber}}", aiFlow: "CardOps" });
check(tpl.status === 200 && tpl.preview === "template-variable" && tpl.body?.data?.cards?.[0]?.cardNumber === "540000******1234", "template preview", `${tpl.status} preview=${tpl.preview}`);
const get = await fetch(`${base}/voice/v1/cards.list`);
check(get.status === 405, "GET on a service is 405", String(get.status));
const health = await fetch(`${base}/health`);
const hb = await health.json();
check(health.status === 200 && hb.customers === 34 && hb.cards === 65 && hb.fixtures === 617, "health", JSON.stringify(hb).slice(0, 120));
const opt = await fetch(`${base}/voice/v1/cards.list`, { method: "OPTIONS" });
check(opt.status === 204 && opt.headers.get("access-control-allow-origin") === "*", "CORS preflight", String(opt.status));
console.log(`negative / extra checks: ${failures.length === before ? "all passed" : `${failures.length - before} FAILED`}`);

console.log(`\nTOTAL: ${pass} passed, ${failures.length} failed`);
for (const f of failures.slice(0, 40)) console.log("  FAIL", f);
process.exit(failures.length ? 1 : 0);
