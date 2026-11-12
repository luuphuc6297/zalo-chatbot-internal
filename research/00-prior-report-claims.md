# Prior report — claims to verify (baseline)

Source: a report the user pasted on 2026-11-07 (research dated 2026-11-06). The files it referenced (`data/services-source-draft.json`, `zalo-mcp-audit.md`, `zalo-agent-cli-audit.md`) are NOT in this project; treat the report as unverified input. Each claim below has an ID so research agents can mark it CONFIRMED / REFUTED / UNVERIFIABLE / OUTDATED with evidence.

## User's original request (verbatim intent)
Deep dive investigate, analytics, research to build a chatbot that automatically: advises customers, answers the menu, explains service processes, answers expert/professional questions, "chốt lịch" (closes bookings), sends promotional programs, schedules follow-up check-ins. Uses the user's Anthropic subscription and model Opus 5.5. The chatbot is a desktop app that is installed and linked to Zalo OA. Business overview: Google Drive folder (mirrored at `sources/drive/`). Reference repos: ardennguyen/zalo-mcp, PhucMPham/zalo-agent-cli (cloned at `sources/repos/`; also `arden-zalo-agent-cli` = Arden engine).

Scope decided earlier with the user (per prior report): macOS app; Anthropic Ultra plan; Opus 5.5; booking is NOT the first priority and will later connect to a separate booking app.

## Claims

### Business knowledge (sources/drive)
- K1. Bundle `thomhouse-knowledge-bundle.txt` is 578,085 bytes, self-dated 2026-05-16, gathers 30 documents; Drive modified 2025/2026-10-25.
- K2. `documentation/06-brand-voice-identity.md` (modified 2026-11-03, newer than bundle) says default brand name is written `thom house`; `Thơm House` for personal context and Fanpage name.
- K3. 23 services in 5 groups (relaxation, health, women, skin, hair); 33 price variants by duration or time slot.
- K4. Chatbot-fixes section says 1:1 advising bot calls itself `em`, customer `anh/chị`; newer brand-voice file says `mình/bạn` and also mentions customer messages → conflict to resolve.
- K5. Gội đầu thư giãn: 199,000đ for 50 min in 9h–20h30; after 20h30 229,000đ.
- K6. Foot massage priced by duration without day/night split; hair-shaft care (chăm sóc nan tóc) fixed price → per-service price rules needed.
- K7. Docs describe: thank-you within 24h, check-in after 2–3 days, gentle contact after one month (guidance, not approved schedule).
- K8. Opening hours conflict: header says 9h–24h, fixes section says hours pending confirmation (bundle lines ~57 and ~589–603).
- K9. Persona names Thị Thư and Nhã Trúc appear; naming/pronoun conflict.
- K10. Docs forbid cure promises yet describe stroke prevention, tumor reduction, supporting cure of uterine prolapse.
- K11. Tech section claims "20x effectiveness" and asks to quote it without verification (bundle ~4194–4225).
- K12. Device "SHR" and its conditions unclear; Whitetox info incomplete.
- K13. Yoni Retreat 3,500,000đ but later text calls it the second most expensive after a 2,990,000đ service (bundle ~9028–9047).
- K14. Aftercare template treats tiredness from "detox" or mild bloating as normal (bundle ~3550–3608).

### Zalo repos
- R1. ardennguyen/zalo-mcp wrapper 2.0.9 commit 89e209c depends on Arden engine 2.5.9 commit f867f0e.
- R2. Arden engine has an official OA client and OA commands, but MCP tools use personal account via `zca-js`; no OA MCP tools.
- R3. Arden license CC-BY-NC-SA-4.0; NOTICE requires separate license for commercial use.
- R4. PhucMPham/zalo-agent-cli v1.7.0 commit ce630ee, MIT, has an official OA client separate from personal-account integration; its MCP tools use personal account.
- R5. Reminder/auto-reply commands in both are not OA customer-care flows.
- R6. Both verify webhook with HMAC-SHA256 over the request body; Zalo docs specify SHA256 of concatenation appId + data + timestamp + OA secret key → mismatch (not reproduced on a real OA).
- R7. Missing: durable event persistence before ack, dedup, auto token refresh, send-permission checks. PhucMPham uses old transaction/promotion send path, no ZBS template flow.
- R8. Zalo announced stopping old UID-format/old endpoints from 2026-03-01.

### Anthropic
- A1. Ultra plan includes 200 USD monthly API credits; must be eligible and link Claude Console to receive.
- A2. Bot should use a Console API key; must not route customer messages through the Ultra login session (per Claude Code legal/compliance auth rules).
- A3. Opus 5.5 model ID `claude-opus-5-5`, standard price 4 USD / MTok input, 20 USD / MTok output.
- A4. Credits separate from chat usage limits; behavior after credits run out depends on purchased balance/billing config; don't enable auto-reload by default.
- A5. Messages API recommended for v1; Agent SDK only if more complex orchestration needed.
- A6. API data not used for training ≠ not retained; retention policy is separate.
- A7. Usage Policy currently shows effective date 2026-11-12.

### Zalo platform
- Z1. OA OpenAPI "Tin Tư vấn" (consultation message) window: up to 7 days since user's last valid interaction; free in first 48h; fee beyond 48h. OA Manager has a different window.
- Z2. Following the OA alone does not grant permission to send all consultation messages.
- Z3. Proactive reminders/promotions must use correct message type; ZBS Template Message = Zalo-approved template with parameters; having a template does not mean every customer is eligible.
- Z4. Access token valid 25 hours; refresh token single-use.
- Z5. Pricing: "Tăng trưởng" package 1,400,000đ / 6 months or 2,500,000đ / year incl. VAT, supports API; consultation message beyond 48h costs 55đ/message outside quota.

### Architecture / cost
- C1. Recommended: macOS app (Electron + TypeScript) for staff + always-on server (TypeScript, PostgreSQL, DB-backed job worker); running everything on a Mac is OK only for internal testing.
- C2. Cost example: 1,000 conversations/month × 6 model calls; 2,000 in + 400 out tokens/call → 96 USD; 6,000 in + 800 out → 240 USD.
- C3. Three modes: draft-only, staff approves each message, auto-reply for allowed situations; flags `auto_reply_enabled`, `scheduled_sends_enabled` checked right before sending.
