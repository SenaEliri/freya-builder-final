// Worker entry point. Only the default export lives here: workerd treats every named export
// of the entry module as a handler, so helpers and constants are exported from ./handler instead.
import { createHandler } from "./handler";

export default { fetch: createHandler() };
