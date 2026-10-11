// Turns the bank's fixture file into one request per fixture. Shared by the tests and scripts/replay.mjs
// (which re-implements the same walk in plain JS so it can run without a build step).
import raw from "../fixtures/test-customers.json";

export interface Case {
  name: string;
  service: string;
  customerNo: string;
  data: Record<string, unknown>;
  http: number;
  response: unknown;
  delaySeconds?: number;
}

interface Entry {
  http: number;
  response: unknown;
  delaySeconds?: number;
}
interface Customer {
  customerNo: string;
  services: Record<string, unknown>;
}

export const customers = (raw as unknown as { customers: Customer[] }).customers;

export function requestData(service: string, customerNo: string, card?: string, week?: string): Record<string, unknown> {
  switch (service) {
    case "cards.list":
      return { customerNo, aiFlow: "CardOps" };
    case "cards.balance":
    case "statement.week.get":
      return { cardNumber: card };
    case "statement.week.decide":
    case "statement.week.change":
      return { cardNumber: card, newStatementWeek: Number(week), statementDay: 5 };
    case "contact.email.get":
      return { customerNo, intAddressInfoType: "E" };
    case "statement.pdf.send":
      return { customerNo, cardNumber: "540000******1234", currencyType: "TL", statementDate: "05.10.2026", emailAddress: "ornek@freyabank.example" };
    default:
      throw new Error(`unknown service ${service}`);
  }
}

export function allCases(): Case[] {
  const cases: Case[] = [];
  const add = (service: string, customerNo: string, e: Entry, card?: string, week?: string) =>
    cases.push({
      name: [service, customerNo, card, week && `week ${week}`].filter(Boolean).join(" "),
      service,
      customerNo,
      data: requestData(service, customerNo, card, week),
      http: e.http,
      response: e.response,
      delaySeconds: e.delaySeconds,
    });
  for (const c of customers) {
    for (const [service, node] of Object.entries(c.services)) {
      if (service === "cards.list" || service === "contact.email.get" || service === "statement.pdf.send") {
        add(service, c.customerNo, node as Entry);
      } else if (service === "cards.balance" || service === "statement.week.get") {
        for (const [card, e] of Object.entries(node as Record<string, Entry>)) add(service, c.customerNo, e, card);
      } else {
        for (const [card, weeks] of Object.entries(node as Record<string, Record<string, Entry>>))
          for (const [week, e] of Object.entries(weeks)) add(service, c.customerNo, e, card, week);
      }
    }
  }
  return cases;
}
