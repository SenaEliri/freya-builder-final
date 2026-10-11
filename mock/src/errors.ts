// Contract-shaped error envelopes (service contract section 4) for requests that have no fixture.
// Errors that exist in the fixture file are never rebuilt here; they are served verbatim.

const ERROR_ORIGIN = "ivr-gateway-test:ivr-channel-v0";
const NOT_FOUND_CAUSE = "com.freyabank.ivrgateway.ivrchannel.rest.exception.NotFoundException";

export interface ErrorSpec {
  http: number;
  code: string;
  message: string;
  type: "ERROR" | "WARNING";
  rootCause: string;
}

export function invalidArguments(message: string): ErrorSpec {
  return { http: 400, code: "INVALID_ARGUMENTS_ERROR", message, type: "ERROR", rootCause: "InvalidArgumentsException" };
}

function notFound(code: string, message: string): ErrorSpec {
  return { http: 404, code, message, type: "WARNING", rootCause: NOT_FOUND_CAUSE };
}

export const NOT_FOUND = {
  "cards.list": notFound("FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."),
  "cards.balance": notFound("FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"),
  "statement.week.get": notFound("FB_IVR_CHANNEL_121", "Hesap kesim servisi hatası: kart bulunamadı"),
  "statement.pdf.send": notFound("FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"),
} as const;

export function errorBody(spec: ErrorSpec): unknown {
  const guid = crypto.randomUUID().replace(/-/g, "");
  return {
    result: {
      guid,
      returnCode: spec.code,
      messageText: spec.message,
      code: spec.code,
      message: spec.message,
      type: spec.type,
      details: { guid, rootCause: spec.rootCause, errorOrigin: ERROR_ORIGIN },
    },
  };
}
