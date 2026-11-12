// Types for `cloudflare:test` env inside tests.
import type { Env as AppBindings } from '../src/types';

declare global {
  namespace Cloudflare {
    interface Env extends AppBindings {
      TEST_MIGRATIONS: import('cloudflare:test').D1Migration[];
    }
  }
}
export {};
