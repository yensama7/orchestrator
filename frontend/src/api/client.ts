// Typed client over the generated OpenAPI `paths` (Phase 5). Same runtime as the
// old untyped fetch helpers — the only thing added is that endpoint names and
// their request/response shapes are checked against the backend contract. A wrong
// path or body now fails `tsc` instead of at runtime.
import type { paths } from "./schema";

type ApiPath = keyof paths;

// Paths that actually define a GET / POST (openapi-typescript emits `get?: never`
// for the rest, so we key off the operation's `responses`).
export type GetPath = { [P in ApiPath]: paths[P]["get"] extends { responses: unknown } ? P : never }[ApiPath];
export type PostPath = { [P in ApiPath]: paths[P]["post"] extends { responses: unknown } ? P : never }[ApiPath];

// `useApi` addresses endpoints by the `/api/`-less key (see api.ts), so expose
// that stripped union for its key constraint.
type StripApi<P extends string> = P extends `/api/${infer R}` ? R : never;
export type GetKey = StripApi<GetPath & string>;

type Json<O> = O extends { responses: { 200: { content: { "application/json": infer R } } } } ? R : unknown;
export type GetResponse<P extends GetPath> = paths[P] extends { get: infer O } ? Json<O> : unknown;
type PostResponse<P extends PostPath> = paths[P] extends { post: infer O } ? Json<O> : unknown;
type PostBody<P extends PostPath> = paths[P] extends { post: { requestBody: { content: { "application/json": infer B } } } }
	? B
	: undefined;

export async function apiGet<P extends GetPath>(path: P, query?: Record<string, string>): Promise<GetResponse<P>> {
	const q = query ? `?${new URLSearchParams(query)}` : "";
	return fetch(`${path}${q}`).then((r) => r.json());
}

export async function apiPost<P extends PostPath>(path: P, body?: PostBody<P>): Promise<PostResponse<P>> {
	const r = await fetch(path, {
		method: "POST",
		headers: { "content-type": "application/json" },
		body: body ? JSON.stringify(body) : undefined,
	});
	return r.json().catch(() => ({}) as PostResponse<P>);
}
