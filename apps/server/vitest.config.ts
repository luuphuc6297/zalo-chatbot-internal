// Tests run inside workerd via @cloudflare/vitest-plugin (successor of @cloudflare/vitest-pool-workers).
// D1 starts empty per test file; test/apply-migrations.ts applies migrations/ before each file.
import { cloudflareTest, readD1Migrations } from '@cloudflare/vitest-plugin';
import { defineConfig } from 'vitest/config';

export default defineConfig(async () => {
  const migrations = await readD1Migrations(new URL('./migrations', import.meta.url).pathname);
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            ENV: 'dev',
            RUNNER_TOKEN: 'test-runner-token',
            STAFF_TOKEN: 'test-staff-token',
            ZALO_APP_ID: 'test-app-id',
            ZALO_OA_ID: 'test-oa-id',
            ZALO_OA_SECRET_KEY: 'test-oa-secret',
            ZALO_APP_SECRET_KEY: 'test-app-secret',
            // Pinned so a local .dev.vars (ZALO_MODE=personal, real secrets) never changes test behaviour.
            ZALO_MODE: 'mock',
            ZALO_PERSONAL_WEBHOOK_SECRET: 'test-personal-webhook-secret',
            // Bridge send limits off by default (claims follow each other within milliseconds in tests); the tests
            // of those limits pass their own values.
            PERSONAL_SEND_MAX_PER_HOUR: '0',
            PERSONAL_THREAD_MIN_GAP_MS: '0',
          },
        },
      }),
    ],
    test: { setupFiles: ['./test/apply-migrations.ts'] },
  };
});
