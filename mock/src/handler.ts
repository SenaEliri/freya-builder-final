// Freya Bank voice services mock (statement / debt use case).
// Serves the bank's test-environment fixtures verbatim: same paths, status codes and bodies.
import { errorBody, invalidArguments, NOT_FOUND, type ErrorSpec } from "./errors";
import { cardFixture, customerFixture, firstWeek, SERVICES, STATS, weekFixture, type Fixture, type Service } from "./fixtures";

const BASE_PATH = "/voice/v1/";
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "X-Mock-Preview" };

// Fixture served when the Freya panel's "Test API Request" button sends an unfilled {{variable}}.
// Customer 90000001 (Ada Örnek) is the contract's own example and answers 200 on all seven services.
export const PREVIEW_CUSTOMER = "90000001";
export const PREVIEW_CARD = "540000******1234";

type Data = Record<string, unknown>;
type Outcome = { fixture: Fixture; preview: boolean } | { error: ErrorSpec };

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return Response.json(body, { status, headers: { ...CORS, ...headers } });
}

// The panel's "Test API Request" button sends variables without filling them in, e.g. "{{customerNumber}}".
export function isTemplateVariable(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const v = value.trim();
  return v.startsWith("{{") || v.toUpperCase().startsWith("%7B%7B");
}

/** Strings are trimmed, numbers stringified; anything else (or empty) counts as missing. */
function text(value: unknown): string | undefined {
  if (typeof value === "string") return value.trim() || undefined;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return undefined;
}

function missing(data: Data, fields: readonly string[]): ErrorSpec | undefined {
  for (const f of fields) if (text(data[f]) === undefined) return invalidArguments(`${LABELS[f] ?? f} cannot be empty`);
  return undefined;
}

const LABELS: Record<string, string> = {
  customerNo: "customer number",
  cardNumber: "card number",
};

const REQUIRED: Record<Service, readonly string[]> = {
  "cards.list": ["customerNo"],
  "cards.balance": ["cardNumber"],
  "statement.week.get": ["cardNumber"],
  "statement.week.decide": ["cardNumber", "newStatementWeek", "statementDay"],
  "statement.week.change": ["cardNumber", "newStatementWeek", "statementDay"],
  "contact.email.get": ["customerNo", "intAddressInfoType"],
  "statement.pdf.send": ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"],
};

function resolve(service: Service, data: Data): Outcome {
  const invalid = missing(data, REQUIRED[service]);
  if (invalid) return { error: invalid };

  switch (service) {
    case "cards.list":
    case "contact.email.get":
    case "statement.pdf.send": {
      const preview = isTemplateVariable(data.customerNo);
      const customerNo = preview ? PREVIEW_CUSTOMER : text(data.customerNo)!;
      const fixture = customerFixture(service, customerNo);
      if (fixture) return { fixture, preview };
      return { error: service === "contact.email.get" ? invalidArguments(`customer ${customerNo} not found`) : NOT_FOUND[service] };
    }
    case "cards.balance":
    case "statement.week.get": {
      const preview = isTemplateVariable(data.cardNumber);
      const fixture = cardFixture(service, preview ? PREVIEW_CARD : text(data.cardNumber)!);
      return fixture ? { fixture, preview } : { error: NOT_FOUND[service] };
    }
    case "statement.week.decide":
    case "statement.week.change": {
      const previewCard = isTemplateVariable(data.cardNumber);
      const previewWeek = isTemplateVariable(data.newStatementWeek);
      const card = previewCard ? PREVIEW_CARD : text(data.cardNumber)!;
      const week = previewWeek ? firstWeek(service, card) : text(data.newStatementWeek)!;
      const fixture = week === undefined ? undefined : weekFixture(service, card, week);
      if (fixture) return { fixture, preview: previewCard || previewWeek };
      return { error: invalidArguments(`statement week ${week ?? "?"} is not available for card ${card}`) };
    }
  }
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

async function handleService(service: Service, request: Request, wait: (ms: number) => Promise<void>): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse(invalidArguments("request body is not valid JSON"));
  }
  const data = (body as { data?: unknown } | null)?.data;
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return errorResponse(invalidArguments("data cannot be empty"));
  }

  const outcome = resolve(service, data as Data);
  if ("error" in outcome) return errorResponse(outcome.error);

  const { fixture, preview } = outcome;
  if (fixture.delaySeconds) await wait(fixture.delaySeconds * 1000);
  return json(fixture.response, fixture.http, preview ? { "X-Mock-Preview": "template-variable" } : {});
}

function errorResponse(spec: ErrorSpec, headers: Record<string, string> = {}): Response {
  return json(errorBody(spec), spec.http, headers);
}

export function createHandler(wait: (ms: number) => Promise<void> = sleep) {
  return async function fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.length > 1 ? url.pathname.replace(/\/+$/, "") : url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: { ...CORS, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "*", "Access-Control-Max-Age": "86400" },
      });
    }
    if (request.method === "GET" && (path === "/health" || path === "/")) {
      return json({ status: "ok", ...STATS, services: SERVICES.map((s) => `POST ${BASE_PATH}${s}`) });
    }

    const service = path.startsWith(BASE_PATH) ? (path.slice(BASE_PATH.length) as Service) : undefined;
    if (service !== undefined && SERVICES.includes(service)) {
      if (request.method !== "POST") {
        return errorResponse(
          { http: 405, code: "METHOD_NOT_ALLOWED", message: `${service} only accepts POST`, type: "ERROR", rootCause: "MethodNotAllowedException" },
          { Allow: "POST, OPTIONS" },
        );
      }
      return handleService(service, request, wait);
    }
    return errorResponse({ http: 404, code: "NOT_FOUND", message: `no such service: ${request.method} ${url.pathname}`, type: "ERROR", rootCause: "NoRouteException" });
  };
}
