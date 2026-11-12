// Owner: server-core. Error envelope + helpers used by every route (docs/contracts.md "Errors").
import type { Context } from 'hono';
import type { ContentfulStatusCode } from 'hono/utils/http-status';
import type { AppEnv, ErrorCode } from '../types';

export class HttpError extends Error {
  constructor(
    public status: ContentfulStatusCode,
    public code: ErrorCode,
    message: string,
    public details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

export class NotImplementedError extends HttpError {
  constructor(what: string) {
    super(501, 'not_implemented', `${what} is not implemented yet`);
  }
}

export function errorJson(
  c: Context<AppEnv>,
  status: ContentfulStatusCode,
  code: ErrorCode,
  message: string,
  details?: Record<string, unknown>,
): Response {
  return c.json({ error: { code, message, ...(details ? { details } : {}) } }, status);
}

/** Hono onError handler: HttpError -> its envelope, anything else -> 500 internal (no stack to clients). */
export function onError(err: Error, c: Context<AppEnv>): Response {
  if (err instanceof HttpError) return errorJson(c, err.status, err.code, err.message, err.details);
  console.error(JSON.stringify({ level: 'error', request_id: c.get('requestId'), message: err.message }));
  return errorJson(c, 500, 'internal', 'internal error');
}

export async function readJson<T>(c: Context<AppEnv>): Promise<T> {
  try {
    return (await c.req.json()) as T;
  } catch {
    throw new HttpError(400, 'bad_request', 'body must be JSON');
  }
}

// ---- Workers RPC carries only an error's message across the Durable Object boundary, so HttpErrors thrown inside
// the Conversation DO are encoded into the message and decoded by the calling handler.
const RPC_ERR_PREFIX = '__http_error__';

export function toRpcError(e: unknown): Error {
  if (e instanceof HttpError) {
    return new Error(RPC_ERR_PREFIX + JSON.stringify({ status: e.status, code: e.code, message: e.message, details: e.details }));
  }
  return e instanceof Error ? e : new Error(String(e));
}

/** Converts an encoded DO error back into an HttpError; other errors are returned unchanged. */
export function fromRpcError(e: unknown): unknown {
  const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : '';
  const i = msg.indexOf(RPC_ERR_PREFIX);
  if (i < 0) return e;
  try {
    const o = JSON.parse(msg.slice(i + RPC_ERR_PREFIX.length)) as { status: ContentfulStatusCode; code: ErrorCode; message: string; details?: Record<string, unknown> };
    return new HttpError(o.status, o.code, o.message, o.details);
  } catch {
    return e;
  }
}

/** Expected errors returned (not thrown) by Conversation DO methods, so workerd does not log them as uncaught. */
export interface RpcFailure {
  rpc_error: { status: ContentfulStatusCode; code: ErrorCode; message: string; details?: Record<string, unknown> };
}

export function toRpcFailure(e: unknown): RpcFailure {
  if (e instanceof HttpError) return { rpc_error: { status: e.status, code: e.code, message: e.message, ...(e.details ? { details: e.details } : {}) } };
  throw e;
}

/** Awaits a DO RPC call; a returned RpcFailure or an encoded thrown HttpError becomes an HttpError again. */
export async function rpc<T>(p: Promise<T | RpcFailure>): Promise<T> {
  let r: T | RpcFailure;
  try {
    r = await p;
  } catch (e) {
    throw fromRpcError(e);
  }
  if (r && typeof r === 'object' && 'rpc_error' in (r as object)) {
    const f = (r as RpcFailure).rpc_error;
    throw new HttpError(f.status, f.code, f.message, f.details);
  }
  return r as T;
}
