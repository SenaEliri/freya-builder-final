// Lookup indexes over the bank's fixture file. Built once at module load, never per request.
import raw from "../fixtures/test-customers.json";

export interface Fixture {
  http: number;
  response: unknown;
  delaySeconds?: number;
}

interface CustomerNode {
  customerNo: string;
  services: Record<string, unknown>;
}

export const SERVICES = [
  "cards.list",
  "cards.balance",
  "statement.week.get",
  "statement.week.decide",
  "statement.week.change",
  "contact.email.get",
  "statement.pdf.send",
] as const;
export type Service = (typeof SERVICES)[number];

type CustomerService = "cards.list" | "contact.email.get" | "statement.pdf.send";
type CardService = "cards.balance" | "statement.week.get";
type WeekService = "statement.week.decide" | "statement.week.change";

const CUSTOMER_SERVICES: readonly CustomerService[] = ["cards.list", "contact.email.get", "statement.pdf.send"];
const CARD_SERVICES: readonly CardService[] = ["cards.balance", "statement.week.get"];
const WEEK_SERVICES: readonly WeekService[] = ["statement.week.decide", "statement.week.change"];

const byCustomer: Record<CustomerService, Map<string, Fixture>> = {
  "cards.list": new Map(),
  "contact.email.get": new Map(),
  "statement.pdf.send": new Map(),
};
const byCard: Record<CardService, Map<string, Fixture>> = {
  "cards.balance": new Map(),
  "statement.week.get": new Map(),
};
const byCardWeek: Record<WeekService, Map<string, Map<string, Fixture>>> = {
  "statement.week.decide": new Map(),
  "statement.week.change": new Map(),
};
const cardOwner = new Map<string, string>();

let fixtureCount = 0;

function own(card: string, customerNo: string): void {
  const prev = cardOwner.get(card);
  if (prev !== undefined && prev !== customerNo) throw new Error(`card ${card} belongs to two customers`);
  cardOwner.set(card, customerNo);
}

function put<K>(map: Map<K, Fixture>, key: K, fixture: Fixture, what: string): void {
  if (map.has(key)) throw new Error(`duplicate fixture: ${what}`);
  map.set(key, fixture);
  fixtureCount++;
}

const customers = (raw as unknown as { customers: CustomerNode[] }).customers;
for (const c of customers) {
  for (const s of CUSTOMER_SERVICES) {
    const node = c.services[s] as Fixture | undefined;
    if (node) put(byCustomer[s], c.customerNo, node, `${s} ${c.customerNo}`);
  }
  for (const s of CARD_SERVICES) {
    const node = (c.services[s] ?? {}) as Record<string, Fixture>;
    for (const [card, fixture] of Object.entries(node)) {
      own(card, c.customerNo);
      put(byCard[s], card, fixture, `${s} ${card}`);
    }
  }
  for (const s of WEEK_SERVICES) {
    const node = (c.services[s] ?? {}) as Record<string, Record<string, Fixture>>;
    for (const [card, weeks] of Object.entries(node)) {
      own(card, c.customerNo);
      const weekMap = new Map<string, Fixture>();
      for (const [week, fixture] of Object.entries(weeks)) put(weekMap, week, fixture, `${s} ${card} ${week}`);
      byCardWeek[s].set(card, weekMap);
    }
  }
}

export const STATS = {
  customers: customers.length,
  cards: cardOwner.size,
  fixtures: fixtureCount,
} as const;

export function customerFixture(service: CustomerService, customerNo: string): Fixture | undefined {
  return byCustomer[service].get(customerNo);
}

export function cardFixture(service: CardService, cardNumber: string): Fixture | undefined {
  return byCard[service].get(cardNumber);
}

export function weekFixture(service: WeekService, cardNumber: string, week: string): Fixture | undefined {
  return byCardWeek[service].get(cardNumber)?.get(week);
}

/** Lowest week that has an entry for the card; used only by the template-variable preview. */
export function firstWeek(service: WeekService, cardNumber: string): string | undefined {
  const weeks = byCardWeek[service].get(cardNumber);
  return weeks ? [...weeks.keys()].sort()[0] : undefined;
}
