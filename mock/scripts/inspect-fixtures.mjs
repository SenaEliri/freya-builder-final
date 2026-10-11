// Read-only inspection of the bank's fixture file. Never writes to it.
// Usage: node scripts/inspect-fixtures.mjs [path/to/test-customers.json]
import { readFileSync } from "node:fs";

const path = process.argv[2] ?? new URL("../fixtures/test-customers.json", import.meta.url);
const raw = readFileSync(path, "utf8");
const doc = JSON.parse(raw);

const CARD_SERVICES = ["cards.balance", "statement.week.get"];
const WEEK_SERVICES = ["statement.week.decide", "statement.week.change"];
const CUSTOMER_SERVICES = ["cards.list", "contact.email.get", "statement.pdf.send"];
const ALL = [...CUSTOMER_SERVICES, ...CARD_SERVICES, ...WEEK_SERVICES];

const entries = []; // { customerNo, service, card, week, entry }
const problems = [];
for (const c of doc.customers) {
  for (const [service, node] of Object.entries(c.services)) {
    if (!ALL.includes(service)) problems.push(`unknown service ${service} on ${c.customerNo}`);
    if (CUSTOMER_SERVICES.includes(service)) entries.push({ customerNo: c.customerNo, service, entry: node });
    if (CARD_SERVICES.includes(service))
      for (const [card, entry] of Object.entries(node)) entries.push({ customerNo: c.customerNo, service, card, entry });
    if (WEEK_SERVICES.includes(service))
      for (const [card, weeks] of Object.entries(node))
        for (const [week, entry] of Object.entries(weeks)) entries.push({ customerNo: c.customerNo, service, card, week, entry });
  }
}

const count = (items, key) => items.reduce((m, x) => ((m[key(x)] = (m[key(x)] ?? 0) + 1), m), {});
const section = (t) => console.log(`\n## ${t}`);

section("Totals");
console.log("customers:", doc.customers.length, "| unique customerNo:", new Set(doc.customers.map((c) => c.customerNo)).size);
console.log("customerNo types:", count(doc.customers, (c) => typeof c.customerNo));
console.log("fixtures:", entries.length);
console.log("by service:", count(entries, (e) => e.service));
console.log("by http:", count(entries, (e) => e.entry.http));
console.log("entry key sets:", count(entries, (e) => Object.keys(e.entry).sort().join(",")));

section("Cards");
const listed = new Map(); // card -> [customerNo]
for (const c of doc.customers) {
  const cards = c.services["cards.list"]?.response?.data?.cards ?? [];
  for (const card of cards) listed.set(card.cardNumber, [...(listed.get(card.cardNumber) ?? []), c.customerNo]);
}
const keyed = new Map(); // card -> Set(customerNo) from card-keyed services
for (const e of entries) if (e.card) keyed.set(e.card, (keyed.get(e.card) ?? new Set()).add(e.customerNo));
console.log("unique cards in cards.list:", listed.size, "| unique cards keyed in services:", keyed.size);
console.log("cards owned by >1 customer:", [...keyed].filter(([, s]) => s.size > 1).map(([k]) => k));
console.log("listed but never keyed:", [...listed.keys()].filter((k) => !keyed.has(k)));
console.log("keyed but never listed:", [...keyed.keys()].filter((k) => !listed.has(k)));
console.log("card key formats:", count([...keyed.keys()], (k) => k.replace(/\d/g, "9")));
for (const svc of [...CARD_SERVICES, ...WEEK_SERVICES]) {
  const have = new Set(entries.filter((e) => e.service === svc).map((e) => e.card));
  console.log(`cards without ${svc}:`, [...keyed.keys()].filter((k) => !have.has(k)));
}

section("Duplicate last-4 / product names");
const byLast4 = {};
for (const k of listed.keys()) (byLast4[k.slice(-4)] ??= []).push(k);
console.log("shared last4:", Object.fromEntries(Object.entries(byLast4).filter(([, v]) => v.length > 1)));
for (const c of doc.customers) {
  const cards = c.services["cards.list"]?.response?.data?.cards ?? [];
  const names = count(cards, (x) => x.productName);
  const dup = Object.entries(names).filter(([, n]) => n > 1);
  if (dup.length) console.log(`  ${c.customerNo} same product name:`, dup);
  for (const x of cards) {
    if (x.productName === "") console.log(`  ${c.customerNo} ${x.cardNumber}: EMPTY productName`);
    if (x.productName.length > 30) console.log(`  ${c.customerNo} ${x.cardNumber}: long productName: ${JSON.stringify(x.productName)}`);
    if (x.status !== "A" || x.isMainCard !== true) console.log(`  ${c.customerNo} ${x.cardNumber}: status=${x.status} isMainCard=${x.isMainCard}`);
    if (x.cardNumberLast4 !== x.cardNumber.slice(-4)) problems.push(`last4 mismatch ${x.cardNumber}`);
  }
  const d = c.services["cards.list"]?.response?.data;
  if (d && (d.validCardsCount !== cards.length || d.exitState !== (cards.length === 1 ? "1_CARD" : "MULTI_CARD")))
    console.log(`  ${c.customerNo} cards.list count/exitState unusual:`, d.validCardsCount, d.exitState, cards.length);
}

section("Non-200 fixtures");
for (const e of entries.filter((e) => e.entry.http !== 200))
  console.log(`${e.customerNo} ${e.service} ${e.card ?? ""} ${e.week ?? ""} -> ${e.entry.http}`, JSON.stringify(e.entry.response));

section("Delayed fixtures");
for (const e of entries.filter((e) => "delaySeconds" in e.entry))
  console.log(`${e.customerNo} ${e.service} ${e.card ?? ""} ${e.week ?? ""} delaySeconds=${e.entry.delaySeconds} http=${e.entry.http}`);

section("Customers with missing services");
for (const c of doc.customers) {
  const missing = ALL.filter((s) => !(s in c.services));
  if (missing.length) console.log(c.customerNo, "missing:", missing.join(", "));
}

section("Week keys");
console.log("decide week keys:", count(entries.filter((e) => e.service === "statement.week.decide"), (e) => e.week));
console.log("change week keys:", count(entries.filter((e) => e.service === "statement.week.change"), (e) => e.week));
const weekSets = {};
for (const svc of WEEK_SERVICES) for (const e of entries.filter((e) => e.service === svc)) ((weekSets[e.card] ??= {})[svc] ??= []).push(e.week);
const currentWeek = Object.fromEntries(entries.filter((e) => e.service === "statement.week.get" && e.entry.http === 200).map((e) => [e.card, String(e.entry.response.data.statementWeek)]));
for (const [card, s] of Object.entries(weekSets)) {
  const d = (s["statement.week.decide"] ?? []).join(""), ch = (s["statement.week.change"] ?? []).join("");
  const expected = ["1", "2", "3", "4"].filter((w) => w !== currentWeek[card]).join("");
  if (d !== expected || ch !== expected) console.log(`  ${card}: current=${currentWeek[card]} decide=[${d}] change=[${ch}]`);
}

section("Optional / unusual fields");
const bal = entries.filter((e) => e.service === "cards.balance" && e.entry.http === 200);
for (const blk of ["debtTL", "debtUSD", "debtEUR", "debtGBP"])
  console.log(`balance without ${blk}:`, bal.filter((e) => !(blk in e.entry.response.data)).map((e) => `${e.customerNo}/${e.card}`));
console.log("balance cardNumber formats:", count(bal, (e) => e.entry.response.data.cardNumber.replace(/\d/g, "9")));
console.log("data key sets per service (200 only):");
for (const svc of ALL) console.log(" ", svc, count(entries.filter((e) => e.service === svc && e.entry.http === 200), (e) => Object.keys(e.entry.response.data).join(",")));
console.log("response top-level key sets:", count(entries, (e) => `${e.entry.http}:${Object.keys(e.entry.response).join(",")}`));
console.log("result key sets:", count(entries, (e) => Object.keys(e.entry.response.result).join(",") + " | details: " + Object.keys(e.entry.response.result.details ?? {}).join(",")));
console.log("week.get relationType:", count(entries.filter((e) => e.service === "statement.week.get" && e.entry.http === 200), (e) => JSON.stringify(e.entry.response.data.relationType)));
console.log("contact communicationType/emailEmpty:", count(entries.filter((e) => e.service === "contact.email.get" && e.entry.http === 200), (e) => `${e.entry.response.data.communicationType}/${e.entry.response.data.ibanEmail === ""}`));
console.log("pdf.send exitState:", count(entries.filter((e) => e.service === "statement.pdf.send" && e.entry.http === 200), (e) => e.entry.response.data.exitState));
console.log("week.change data:", count(entries.filter((e) => e.service === "statement.week.change" && e.entry.http === 200), (e) => `${e.entry.response.data.exitState}/${e.entry.response.data.responseCode}/${e.entry.response.data.responseMessage}`));
console.log("week.decide data:", count(entries.filter((e) => e.service === "statement.week.decide" && e.entry.http === 200), (e) => `${e.entry.response.data.responseCode}/${e.entry.response.data.responseMessage}`));

section("Result envelope invariants");
const guids = new Set();
for (const e of entries) {
  const r = e.entry.response.result;
  const where = `${e.customerNo} ${e.service} ${e.card ?? ""} ${e.week ?? ""}`;
  if (r.returnCode !== r.code) problems.push(`returnCode!=code ${where}`);
  if (r.messageText !== r.message) problems.push(`messageText!=message ${where}`);
  if (r.guid !== r.details?.guid) problems.push(`guid!=details.guid ${where}`);
  if ((e.entry.http === 200) !== (r.returnCode === "1")) problems.push(`http/returnCode disagree ${where}`);
  if ((e.entry.http === 200) !== ("data" in e.entry.response)) problems.push(`data presence disagrees with http ${where}`);
  if (guids.has(r.guid)) problems.push(`duplicate guid ${r.guid} ${where}`);
  guids.add(r.guid);
}
console.log("unique guids:", guids.size, "| guid formats:", count([...guids], (g) => (/^[0-9a-f]{32}$/.test(g) ? "32hex" : g)));
console.log("success result variants:", count(entries.filter((e) => e.entry.http === 200), (e) => JSON.stringify({ ...e.entry.response.result, guid: "*", details: { ...e.entry.response.result.details, guid: "*" } })));

section("JSON number round-trip (raw text vs JS double)");
const nums = raw.match(/(?<=[:\[,]\s*)-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?=\s*[,\]}\n])/g) ?? [];
const lossy = nums.filter((n) => Number(n) !== Number(Number(n).toPrecision(15)) || n.replace(/\.0+$|(?<=\.\d*[1-9])0+$/, "").replace(/^-?0+(?=\d)/, "") !== String(Number(n)).replace(/^-/, n.startsWith("-") ? "-" : ""));
console.log("numeric literals:", nums.length, "| not exactly reproduced by JSON.stringify (ignoring trailing zeros):", [...new Set(lossy)].slice(0, 20));

section("Problems");
console.log(problems.length ? problems : "none");
